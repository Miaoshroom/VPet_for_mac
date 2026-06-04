from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.raising.activity import ActivityDefinition
from core.raising.activity_playback import (
    ActivityPlaybackBridge,
    CarePlaybackBridge,
    VisualStateBridge,
)
from core.raising.items import ItemDefinition
from core.raising.pet_state import PetState


class FakeClip:
    def __init__(self, action_id: str, duration_ms: int = 10) -> None:
        self.action_id = action_id
        self.duration_ms = duration_ms
        self.overlay_item_id: str | None = None


class FakeMode:
    def __init__(self, action_id: str, *, phased: bool = True) -> None:
        self.action_id = action_id
        self.is_phased = phased
        self.start = FakeClip(action_id, 10) if phased else None
        self.loop = FakeClip(action_id, 20)
        self.end = FakeClip(action_id, 10) if phased else None


class FakeCatalog:
    def __init__(self) -> None:
        self.types = {
            "work_live": "phased",
            "work_clean": "phased",
            "default": "loop",
            "eat": "single",
            "drink": "single",
            "gift": "single",
            "sleep": "phased",
            "yawning": "loop",
        }
        self.single_available = {"eat", "drink", "gift"}

    def has_action(self, action_id: str) -> bool:
        return action_id in self.types

    def action_type(self, action_id: str) -> str:
        return self.types[action_id]

    def is_single_available(self, action_id: str, pet_state: str) -> bool:
        del pet_state
        return action_id in self.single_available

    def single_for(self, action_id: str, pet_state: str) -> FakeClip:
        del pet_state
        if action_id not in self.single_available:
            raise KeyError(action_id)
        return FakeClip(action_id)


class FakeDirector:
    def __init__(self) -> None:
        self.pet_state_value = "normal"
        self.current_mode = "default"
        self.available = {"work_clean", "default", "sleep", "yawning"}
        self.interaction_active = False
        self.visual_override_active = False
        self.started_interactions: list[str] = []
        self.ended_interactions = 0
        self.stopped_interactions = 0
        self.set_states: list[str] = []

    def current_mode_name(self) -> str:
        return self.current_mode

    def is_interaction_active(self) -> bool:
        return self.interaction_active

    def is_mode_available(self, mode_name: str) -> bool:
        return mode_name in self.available

    def is_visual_override_active(self) -> bool:
        return self.visual_override_active

    def mode_for_action(self, mode_name: str) -> FakeMode:
        if mode_name not in self.available:
            raise KeyError(mode_name)
        return FakeMode(mode_name, phased=self.available_type(mode_name) == "phased")

    def available_type(self, mode_name: str) -> str:
        return "loop" if mode_name in {"default", "yawning"} else "phased"

    def pet_state(self) -> str:
        return self.pet_state_value

    def set_pet_state(self, pet_state: str, *, resume: bool = True) -> None:
        del resume
        self.pet_state_value = pet_state
        self.set_states.append(pet_state)

    def start_default_mode(self) -> None:
        self.current_mode = "default"

    def start_interaction(self, interaction_name: str):
        if interaction_name not in self.available:
            raise KeyError(interaction_name)
        self.interaction_active = True
        self.started_interactions.append(interaction_name)
        return FakeMode(interaction_name, phased=True)

    def end_interaction(self) -> None:
        self.interaction_active = False
        self.ended_interactions += 1

    def stop_active_interaction(self, *, resume: bool = True) -> bool:
        del resume
        if not self.interaction_active:
            return False
        self.interaction_active = False
        self.stopped_interactions += 1
        return True

    def switch_mode(self, mode_name: str) -> None:
        if mode_name not in self.available:
            raise KeyError(mode_name)
        self.current_mode = mode_name


class FakeSinglePlayer:
    def __init__(self) -> None:
        self.played: list[FakeClip] = []
        self.finished_callbacks: list[object] = []
        self.allow_play = True

    def play(
        self,
        clip: FakeClip,
        on_finished=None,
        *,
        resume: bool = True,
        interruptible: bool = False,
    ) -> bool:
        del resume, interruptible
        if not self.allow_play:
            return False
        self.played.append(clip)
        self.finished_callbacks.append(on_finished)
        return True

    def finish_last(self) -> None:
        callback = self.finished_callbacks[-1]
        if callable(callback):
            callback()


def _activity() -> ActivityDefinition:
    return ActivityDefinition(
        id="work",
        name="短工作",
        category="工作",
        duration_seconds=120,
        costs={},
        rewards={},
        requirements={},
        animation_candidates=("missing", "work_live", "work_clean"),
    )


def _rest_activity() -> ActivityDefinition:
    return ActivityDefinition(
        id="rest",
        name="小睡休息",
        category="休息",
        duration_seconds=120,
        costs={},
        rewards={"energy": 8, "mood": 4},
        requirements={"health": 10},
        animation_candidates=("missing", "sleep", "yawning", "boring"),
    )


class ActivityPlaybackBridgeTest(unittest.TestCase):
    def test_start_uses_first_candidate_available_in_current_state(self) -> None:
        director = FakeDirector()
        bridge = ActivityPlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            single_active=lambda: False,
        )

        result = bridge.start_activity_animation(_activity())

        self.assertTrue(result.started)
        self.assertEqual(result.action_id, "work_clean")
        self.assertEqual(director.started_interactions, ["work_clean"])

    def test_finish_ends_activity_interaction(self) -> None:
        director = FakeDirector()
        bridge = ActivityPlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            single_active=lambda: False,
        )

        bridge.start_activity_animation(_activity())
        bridge.finish_activity_animation()

        self.assertFalse(director.is_interaction_active())
        self.assertEqual(director.ended_interactions, 1)

    def test_start_check_reuses_existing_blockers(self) -> None:
        director = FakeDirector()
        bridge = ActivityPlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: True,
            single_active=lambda: False,
        )

        check = bridge.can_start_activity()

        self.assertFalse(check.ok)
        self.assertIn("插件", check.message)

    def test_start_animation_direct_call_rejects_existing_blockers(self) -> None:
        director = FakeDirector()
        blocked = True
        bridge = ActivityPlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: blocked,
            single_active=lambda: False,
        )

        result = bridge.start_activity_animation(_activity())

        self.assertFalse(result.started)
        self.assertIn("插件", result.message)
        self.assertEqual(director.started_interactions, [])

    def test_rest_activity_uses_sleep_candidate_when_available(self) -> None:
        director = FakeDirector()
        bridge = ActivityPlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            single_active=lambda: False,
        )

        result = bridge.start_activity_animation(_rest_activity())

        self.assertTrue(result.started)
        self.assertEqual(result.action_id, "sleep")
        self.assertEqual(director.started_interactions, ["sleep"])

    def test_activity_without_available_animation_keeps_numeric_activity(self) -> None:
        director = FakeDirector()
        catalog = FakeCatalog()
        catalog.types.pop("sleep")
        catalog.types.pop("yawning")
        bridge = ActivityPlaybackBridge(
            director,
            catalog,
            action_blocked=lambda: False,
            single_active=lambda: False,
        )

        result = bridge.start_activity_animation(_rest_activity())

        self.assertFalse(result.started)
        self.assertIsNone(result.action_id)
        self.assertIn("数值活动", result.message)

    def test_suspend_activity_animation_stops_phased_interaction_without_settling(self) -> None:
        director = FakeDirector()
        bridge = ActivityPlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            single_active=lambda: False,
        )

        bridge.start_activity_animation(_activity())
        result = bridge.suspend_activity_animation()

        self.assertEqual(result.action_id, "work_clean")
        self.assertFalse(bridge.is_active())
        self.assertFalse(director.is_interaction_active())
        self.assertEqual(director.stopped_interactions, 1)


class CarePlaybackBridgeTest(unittest.TestCase):
    def test_allowed_care_plays_single_animation(self) -> None:
        director = FakeDirector()
        single = FakeSinglePlayer()
        bridge = CarePlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            activity_active=lambda: False,
            single_active=lambda: False,
            schedule_once=lambda delay_ms, callback: None,
        )
        bridge.set_single_player(single)

        check = bridge.can_start_care()
        self.assertTrue(check.ok)
        playback = bridge.start_care_animation("simple_feed")

        self.assertTrue(playback.started)
        self.assertEqual(playback.action_id, "eat")
        self.assertEqual([clip.action_id for clip in single.played], ["eat"])

        self.assertTrue(bridge.is_active())
        single.finish_last()
        self.assertFalse(bridge.is_active())

    def test_medicine_care_reuses_eat_animation(self) -> None:
        director = FakeDirector()
        single = FakeSinglePlayer()
        bridge = CarePlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            activity_active=lambda: False,
            single_active=lambda: False,
            schedule_once=lambda delay_ms, callback: None,
        )
        bridge.set_single_player(single)

        playback = bridge.start_care_animation("medicine")

        self.assertTrue(playback.started)
        self.assertEqual(playback.action_id, "eat")
        self.assertEqual([clip.action_id for clip in single.played], ["eat"])

    def test_single_care_passes_item_to_overlay_factory(self) -> None:
        director = FakeDirector()
        director.pet_state_value = "ill"
        single = FakeSinglePlayer()
        item = ItemDefinition(
            id="rice_ball",
            name="饭团",
            category="food",
            price=12,
            effects={"satiety": 24},
            icon="rice_ball.png",
        )

        def overlay_factory(
            clip: FakeClip,
            overlay_item: ItemDefinition,
            pet_state: str,
        ) -> FakeClip:
            wrapped = FakeClip(clip.action_id, clip.duration_ms)
            wrapped.overlay_item_id = f"{overlay_item.id}:{pet_state}"
            return wrapped

        bridge = CarePlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            activity_active=lambda: False,
            single_active=lambda: False,
            schedule_once=lambda delay_ms, callback: None,
            care_clip_overlay=overlay_factory,
        )
        bridge.set_single_player(single)

        playback = bridge.start_care_animation("simple_feed", item=item)

        self.assertTrue(playback.started)
        self.assertEqual(single.played[0].action_id, "eat")
        self.assertEqual(single.played[0].overlay_item_id, "rice_ball:ill")

    def test_gift_care_plays_gift_animation(self) -> None:
        director = FakeDirector()
        single = FakeSinglePlayer()
        bridge = CarePlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            activity_active=lambda: False,
            single_active=lambda: False,
            schedule_once=lambda delay_ms, callback: None,
        )
        bridge.set_single_player(single)

        playback = bridge.start_care_animation("gift")

        self.assertTrue(playback.started)
        self.assertEqual(playback.action_id, "gift")
        self.assertEqual([clip.action_id for clip in single.played], ["gift"])

    def test_care_start_check_rejects_plugin_activity_and_current_action(self) -> None:
        cases = (
            ("plugin", lambda director: True, lambda: False, lambda: False, "插件"),
            ("activity", lambda director: False, lambda: True, lambda: False, "活动"),
            ("single", lambda director: False, lambda: False, lambda: True, "当前动作"),
            ("interaction", lambda director: False, lambda: False, lambda: False, "当前动作"),
        )
        for name, plugin_blocked, activity_active, single_active, message in cases:
            with self.subTest(name=name):
                director = FakeDirector()
                if name == "interaction":
                    director.interaction_active = True
                bridge = CarePlaybackBridge(
                    director,
                    FakeCatalog(),
                    action_blocked=lambda d=director: plugin_blocked(d),
                    activity_active=activity_active,
                    single_active=single_active,
                    schedule_once=lambda delay_ms, callback: None,
                )

                check = bridge.can_start_care()

                self.assertFalse(check.ok)
                self.assertIn(message, check.message)

    def test_missing_care_animation_reports_fallback_message(self) -> None:
        director = FakeDirector()
        catalog = FakeCatalog()
        catalog.types.pop("eat")
        bridge = CarePlaybackBridge(
            director,
            catalog,
            action_blocked=lambda: False,
            activity_active=lambda: False,
            single_active=lambda: False,
            schedule_once=lambda delay_ms, callback: None,
        )

        playback = bridge.start_care_animation("simple_feed")

        self.assertFalse(playback.started)
        self.assertIn("没有可用照顾动画", playback.message)

    def test_phased_care_stays_active_until_playback_idle(self) -> None:
        director = FakeDirector()
        scheduled: list[object] = []
        finished = 0

        def on_finished() -> None:
            nonlocal finished
            finished += 1

        bridge = CarePlaybackBridge(
            director,
            FakeCatalog(),
            action_blocked=lambda: False,
            activity_active=lambda: False,
            single_active=lambda: False,
            schedule_once=lambda delay_ms, callback: scheduled.append(callback),
            on_finished=on_finished,
        )

        result = bridge.start_care_animation("simple_clean")

        self.assertTrue(result.started)
        self.assertEqual(result.action_id, "work_clean")
        self.assertTrue(bridge.is_active())
        self.assertEqual(director.started_interactions, ["work_clean"])

        scheduled[0]()
        self.assertTrue(bridge.is_active())
        self.assertFalse(director.is_interaction_active())

        bridge.on_playback_idle()
        self.assertFalse(bridge.is_active())
        self.assertEqual(finished, 1)


class VisualStateBridgeTest(unittest.TestCase):
    def test_visual_state_applies_when_idle(self) -> None:
        director = FakeDirector()
        state = PetState(mood=90, health=100)
        bridge = VisualStateBridge(
            state,
            director,
            action_blocked=lambda: False,
            single_active=lambda: False,
            activity_animation_active=lambda: False,
        )

        result = bridge.request_update()

        self.assertTrue(result.applied)
        self.assertEqual(director.pet_state(), "happy")

    def test_visual_state_pends_until_blocker_clears(self) -> None:
        director = FakeDirector()
        state = PetState(health=10)
        blocked = True
        bridge = VisualStateBridge(
            state,
            director,
            action_blocked=lambda: blocked,
            single_active=lambda: False,
            activity_animation_active=lambda: False,
        )

        result = bridge.request_update()
        self.assertTrue(result.pending)
        self.assertEqual(director.pet_state(), "normal")

        blocked = False
        result = bridge.apply_pending_if_possible()

        self.assertTrue(result.applied)
        self.assertEqual(director.pet_state(), "ill")

    def test_visual_state_pends_during_care_and_applies_after_finish(self) -> None:
        director = FakeDirector()
        state = PetState(health=10)
        care_active = True
        bridge = VisualStateBridge(
            state,
            director,
            action_blocked=lambda: False,
            single_active=lambda: False,
            activity_animation_active=lambda: False,
            care_animation_active=lambda: care_active,
        )

        result = bridge.request_update()
        self.assertTrue(result.pending)
        self.assertEqual(director.pet_state(), "normal")

        care_active = False
        result = bridge.apply_pending_if_possible()

        self.assertTrue(result.applied)
        self.assertEqual(director.pet_state(), "ill")


if __name__ == "__main__":
    unittest.main()

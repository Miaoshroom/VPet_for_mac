from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.raising.activity import (
    ActivityCatalog,
    ActivityDefinition,
    ActivitySystem,
    load_activity_catalog,
)
from core.raising.activity_playback import ActivityPlaybackResult, PlaybackStartCheck
from core.interaction_map import InteractionBehavior
from core.raising.pet_state import DEFAULT_ACTIVITY, PetState
from core.raising.save_game import SaveGame
from ui.pet_window import PetWindow

ACTIVITY_HIDDEN_SYNC_LIMIT_MS = 30
ACTIVITY_VISIBLE_SYNC_LIMIT_MS = 200


def _catalog() -> ActivityCatalog:
    return ActivityCatalog(
        [
            ActivityDefinition(
                id="work",
                name="短工作",
                category="工作",
                duration_seconds=120,
                requirements={"energy": 20, "mood": 10},
                costs={"energy": 10, "mood": 4},
                rewards={"money": 20},
                animation_id="work_clean",
            ),
            ActivityDefinition(
                id="study",
                name="短学习",
                category="学习",
                duration_seconds=120,
                requirements={"energy": 20, "mood": 10},
                costs={"energy": 8, "mood": 4},
                rewards={"exp": 18},
                animation_candidates=("study", "study_two"),
            ),
            ActivityDefinition(
                id="play",
                name="短娱乐",
                category="娱乐",
                duration_seconds=100,
                requirements={"energy": 10},
                costs={"energy": 6},
                rewards={"mood": 12},
            ),
            ActivityDefinition(
                id="pat",
                name="摸摸头",
                category="日常互动",
                duration_seconds=60,
                requirements={"health": 5},
                costs={},
                rewards={"mood": 4, "affection": 1},
            ),
        ]
    )


class ActivitySystemSmokeTest(unittest.TestCase):
    def test_start_and_complete_work_activity(self) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80))
        system = ActivitySystem(save, _catalog())

        start = system.start("work")
        self.assertTrue(start.ok)
        self.assertTrue(start.changed)
        self.assertEqual(save.pet_state.current_activity, "短工作")
        self.assertIsNotNone(save.activity_progress)

        advance = system.advance(120)
        self.assertTrue(advance.completed)
        self.assertEqual(save.pet_state.money, 20)
        self.assertEqual(save.pet_state.energy, 70)
        self.assertEqual(save.pet_state.mood, 76)
        self.assertEqual(save.pet_state.current_activity, DEFAULT_ACTIVITY)
        self.assertIsNone(save.activity_progress)

    def test_cancel_prorates_rewards_and_costs(self) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80))
        system = ActivitySystem(save, _catalog())

        self.assertTrue(system.start("work").ok)
        self.assertTrue(system.advance(60).changed)
        cancel = system.cancel()

        self.assertTrue(cancel.ok)
        self.assertEqual(cancel.settlement.ratio, 0.5)
        self.assertEqual(save.pet_state.money, 10)
        self.assertEqual(save.pet_state.energy, 75)
        self.assertEqual(save.pet_state.mood, 78)
        self.assertEqual(save.pet_state.current_activity, DEFAULT_ACTIVITY)
        self.assertIsNone(save.activity_progress)

    def test_insufficient_status_blocks_start(self) -> None:
        save = SaveGame(pet_state=PetState(energy=5, mood=80))
        system = ActivitySystem(save, _catalog())

        result = system.start("work")

        self.assertFalse(result.ok)
        self.assertFalse(result.changed)
        self.assertIn("状态不足", result.message)
        self.assertEqual(save.pet_state.money, 0)
        self.assertEqual(save.pet_state.current_activity, DEFAULT_ACTIVITY)
        self.assertIsNone(save.activity_progress)

    def test_only_one_activity_can_run(self) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80))
        system = ActivitySystem(save, _catalog())

        self.assertTrue(system.start("study").ok)
        second = system.start("play")

        self.assertFalse(second.ok)
        self.assertFalse(second.changed)
        self.assertEqual(save.pet_state.current_activity, "短学习")
        self.assertEqual(save.activity_progress.activity_id, "study")

    def test_study_completion_checks_level_up_after_exp_reward(self) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80, health=90, exp=30))
        system = ActivitySystem(save, _catalog())

        self.assertTrue(system.start("study").ok)
        advance = system.advance(120)

        self.assertTrue(advance.completed)
        self.assertIsNotNone(advance.settlement)
        self.assertTrue(advance.settlement.level_result.leveled)
        self.assertEqual(save.pet_state.level, 2)
        self.assertEqual(save.pet_state.exp, 8)
        self.assertEqual(save.pet_state.money, 10)
        self.assertEqual(save.pet_state.affection, 1)
        self.assertEqual(save.pet_state.energy, 74)
        self.assertEqual(save.pet_state.mood, 79)
        self.assertEqual(save.pet_state.health, 91)

    def test_study_cancel_can_also_trigger_level_up_after_prorated_exp(self) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80, health=90, exp=35))
        system = ActivitySystem(save, _catalog())

        self.assertTrue(system.start("study").ok)
        self.assertTrue(system.advance(60).changed)
        cancel = system.cancel()

        self.assertTrue(cancel.ok)
        self.assertIsNotNone(cancel.settlement)
        self.assertTrue(cancel.settlement.level_result.leveled)
        self.assertEqual(cancel.settlement.ratio, 0.5)
        self.assertEqual(save.pet_state.level, 2)
        self.assertEqual(save.pet_state.exp, 4)
        self.assertEqual(save.pet_state.energy, 78)
        self.assertEqual(save.pet_state.mood, 81)

    def test_bundled_catalog_exposes_stage_15_categories(self) -> None:
        catalog = load_activity_catalog()

        categories = tuple(dict.fromkeys(activity.category for activity in catalog.activities()))

        self.assertEqual(categories, ("工作", "学习", "运动", "休息", "日常互动"))
        self.assertTrue(catalog.has("rest_nap"))
        self.assertEqual(catalog.get("play_rope").category, "运动")

    def test_bundled_rest_activity_completes_and_cancel_prorates(self) -> None:
        catalog = load_activity_catalog()
        rest = catalog.get("rest_nap")

        save = SaveGame(pet_state=PetState(energy=50, mood=50, health=80))
        system = ActivitySystem(save, catalog)
        self.assertTrue(system.start(rest.id).ok)
        advance = system.advance(rest.duration_seconds)

        self.assertTrue(advance.completed)
        self.assertEqual(save.pet_state.energy, 66)
        self.assertEqual(save.pet_state.mood, 58)
        self.assertEqual(save.pet_state.current_activity, DEFAULT_ACTIVITY)

        save = SaveGame(pet_state=PetState(energy=50, mood=50, health=80))
        system = ActivitySystem(save, catalog)
        self.assertTrue(system.start(rest.id).ok)
        self.assertTrue(system.advance(rest.duration_seconds // 2).changed)
        cancel = system.cancel()

        self.assertTrue(cancel.ok)
        self.assertEqual(cancel.settlement.ratio, 0.5)
        self.assertEqual(save.pet_state.energy, 58)
        self.assertEqual(save.pet_state.mood, 54)


class FakeActivityPlayback:
    def __init__(self) -> None:
        self.active = False
        self.can_start_ok = True
        self.started: list[str] = []
        self.suspended: list[str] = []

    def can_start_activity(self) -> PlaybackStartCheck:
        return PlaybackStartCheck(self.can_start_ok)

    def is_active(self) -> bool:
        return self.active

    def start_activity_animation(self, activity: ActivityDefinition) -> ActivityPlaybackResult:
        self.active = True
        self.started.append(activity.id)
        return ActivityPlaybackResult(False, None)

    def suspend_activity_animation(self) -> ActivityPlaybackResult:
        self.active = False
        self.suspended.append("activity")
        return ActivityPlaybackResult(False, "work_clean")


class FakeDirector:
    def __init__(self) -> None:
        self.started_interactions: list[str] = []
        self.ended_interactions = 0

    def start_interaction(self, interaction_name: str):
        self.started_interactions.append(interaction_name)
        return object()

    def end_interaction(self) -> None:
        self.ended_interactions += 1


class FakeCarePlayback:
    def __init__(self) -> None:
        self.idle_count = 0

    def on_playback_idle(self) -> None:
        self.idle_count += 1


class FakeStatusPanel:
    def __init__(self) -> None:
        self.notices: list[str] = []
        self.activity_snapshots: list[tuple[object, bool]] = []

    def set_activity_notice(self, message: str) -> None:
        self.notices.append(message)

    def set_activity_snapshot(self, snapshot: object, *, can_start: bool) -> None:
        self.activity_snapshots.append((snapshot, bool(can_start)))


class FakeSignal:
    def __init__(self) -> None:
        self.emit_count = 0

    def emit(self) -> None:
        self.emit_count += 1


class HiddenFakeActivityWindow:
    def __init__(self) -> None:
        self.visible = False
        self.dirty_count = 0
        self.pet_state_energy: list[int] = []
        self.snapshots: list[tuple[object, bool]] = []

    def isVisible(self) -> bool:
        return self.visible

    def mark_dirty(self) -> None:
        self.dirty_count += 1

    def set_pet_state(self, state: PetState) -> None:
        self.pet_state_energy.append(int(state.energy))

    def set_activity_snapshot(self, snapshot: object, *, can_start: bool) -> None:
        self.snapshots.append((snapshot, bool(can_start)))


class PetWindowActivityWindowSyncSmokeTest(unittest.TestCase):
    def _window_like(self, save: SaveGame):
        window = type("WindowLike", (), {})()
        window._save_game = save
        window._activity_system = ActivitySystem(save, _catalog())
        window._activity_playback = FakeActivityPlayback()
        window._activity_window = HiddenFakeActivityWindow()
        return window

    def test_hidden_activity_window_sync_marks_dirty_without_refreshing_widgets(self) -> None:
        from PyQt6.QtCore import QElapsedTimer

        save = SaveGame(pet_state=PetState(energy=80, mood=80, health=80))
        window = self._window_like(save)

        timer = QElapsedTimer()
        timer.start()
        PetWindow._sync_activity_window(window)
        hidden_ms = timer.nsecsElapsed() / 1_000_000

        activity_window = window._activity_window
        self.assertLess(hidden_ms, ACTIVITY_HIDDEN_SYNC_LIMIT_MS)
        self.assertEqual(activity_window.dirty_count, 1)
        self.assertEqual(activity_window.pet_state_energy, [])
        self.assertEqual(activity_window.snapshots, [])

        timer.restart()
        PetWindow._sync_activity_window(window, force=True)
        force_ms = timer.nsecsElapsed() / 1_000_000

        self.assertLess(force_ms, ACTIVITY_VISIBLE_SYNC_LIMIT_MS)
        self.assertEqual(activity_window.pet_state_energy, [80])
        self.assertEqual(len(activity_window.snapshots), 1)

    def test_activity_window_applies_hidden_updates_when_shown(self) -> None:
        from PyQt6.QtCore import QElapsedTimer
        from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton

        from ui.windows.activity_window import ActivityWindow

        app = QApplication.instance() or QApplication([])
        window = ActivityWindow()

        window.set_activities(_catalog().activities())
        window.set_pet_state(PetState(energy=5, mood=80, health=80))
        self.assertTrue(window._activity_sync_dirty)

        timer = QElapsedTimer()
        timer.start()
        window.show_window()
        app.processEvents()
        open_ms = timer.nsecsElapsed() / 1_000_000

        category_combo = window.findChild(QComboBox, "activityCategoryCombo")
        start_button = window.findChild(QPushButton, "activityStartButton")
        self.assertLess(open_ms, ACTIVITY_VISIBLE_SYNC_LIMIT_MS)
        self.assertFalse(window._activity_sync_dirty)
        self.assertIsNotNone(category_combo)
        self.assertGreater(category_combo.count(), 0)
        self.assertIsNotNone(start_button)
        self.assertFalse(start_button.isEnabled())
        self.assertEqual(start_button.text(), "状态不足")


class PetWindowActivityBoundarySmokeTest(unittest.TestCase):
    def _window_like(self, save: SaveGame):
        window = type("WindowLike", (), {})()
        window._save_game = save
        window._activity_system = ActivitySystem(save, _catalog())
        window._activity_playback = FakeActivityPlayback()
        window._director = FakeDirector()
        window._care_playback = FakeCarePlayback()
        window._status_panel = FakeStatusPanel()
        window._request_visual_state_update = lambda: None
        window._sync_status_panel_info = lambda: None
        window._sync_activity_panel = lambda: PetWindow._sync_activity_panel(window)
        window._refresh_dev_debug = lambda: None
        window._start_user_press_interaction = (
            lambda mode: PetWindow._start_user_press_interaction(window, mode)
        )
        window._suspend_activity_animation_for_user_interaction = (
            lambda: PetWindow._suspend_activity_animation_for_user_interaction(window)
        )
        window._resume_activity_animation_if_needed = (
            lambda: PetWindow._resume_activity_animation_if_needed(window)
        )
        window._resume_loaded_activity_animation = (
            lambda: PetWindow._resume_loaded_activity_animation(window)
        )
        window._visual_state_bridge = type(
            "FakeVisualStateBridge",
            (),
            {"apply_pending_if_possible": lambda self: None},
        )()
        window.save_game_changed = FakeSignal()
        return window

    def test_activity_in_progress_cannot_start_second_activity(self) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80, health=80))
        window = self._window_like(save)

        PetWindow._start_activity(window, "work")
        PetWindow._start_activity(window, "study")

        self.assertEqual(save.activity_progress.activity_id, "work")
        self.assertEqual(window._activity_playback.started, ["work"])
        self.assertEqual(window.save_game_changed.emit_count, 1)
        self.assertIn("当前正在进行：短工作", window._status_panel.notices[-1])

    def test_user_press_interaction_suspends_then_resumes_activity_animation(
        self,
    ) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80, health=80))
        window = self._window_like(save)

        PetWindow._start_activity(window, "work")
        started = PetWindow._handle_behavior(
            window,
            InteractionBehavior(type="press_mode", mode="touch_head"),
        )
        PetWindow.on_playback_idle(window)

        self.assertTrue(started)
        self.assertEqual(window._activity_playback.suspended, ["activity"])
        self.assertEqual(window._director.started_interactions, ["touch_head"])
        self.assertEqual(window._activity_playback.started, ["work", "work"])

    def test_playback_idle_refreshes_activity_start_availability(self) -> None:
        save = SaveGame(pet_state=PetState(energy=80, mood=80, health=80))
        window = self._window_like(save)

        window._activity_playback.can_start_ok = False
        PetWindow._sync_activity_panel(window)
        window._activity_playback.can_start_ok = True
        PetWindow.on_playback_idle(window)

        self.assertFalse(window._status_panel.activity_snapshots[0][1])
        self.assertTrue(window._status_panel.activity_snapshots[-1][1])


if __name__ == "__main__":
    unittest.main()

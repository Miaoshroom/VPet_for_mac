from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication

from core.auto_move import AutoMoveController, MoveRule


class FakeClip:
    def __init__(self, duration_ms: int) -> None:
        self.duration_ms = duration_ms


class FakeMode:
    def __init__(self, *, start_ms: int = 100, end_ms: int = 100) -> None:
        self.is_phased = True
        self.start = FakeClip(start_ms)
        self.end = FakeClip(end_ms)


class FakeDirector:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.ended = 0

    def mode_for_action(self, mode_name: str) -> FakeMode:
        del mode_name
        return FakeMode()

    def start_interaction(self, interaction_name: str) -> FakeMode:
        self.started.append(interaction_name)
        return FakeMode()

    def end_interaction(self) -> None:
        self.ended += 1

    def is_interaction_active(self) -> bool:
        return False


class FakeSwitch:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def is_active(self) -> bool:
        return False


class FakeWindow:
    def __init__(self) -> None:
        self._rect = QRect(100, 100, 100, 100)
        self.moves: list[tuple[int, int]] = []

    def geometry(self) -> QRect:
        return QRect(self._rect)

    def x(self) -> int:
        return self._rect.x()

    def y(self) -> int:
        return self._rect.y()

    def move(self, x: int, y: int) -> None:
        self._rect.moveTo(x, y)
        self.moves.append((x, y))

    def screen(self):
        return None


class AutoMoveControllerTest(unittest.TestCase):
    def test_stale_start_and_end_callbacks_do_not_affect_new_move(self) -> None:
        app = QApplication.instance() or QApplication([])
        scheduled: list[tuple[int, object]] = []
        director = FakeDirector()
        single_switch = FakeSwitch()
        mode_switch = FakeSwitch()
        window = FakeWindow()
        controller = AutoMoveController(
            parent=app,
            director=director,
            window=window,
            action_blocked=lambda: False,
            single_autoswitch=single_switch,
            mode_autoswitch=mode_switch,
            single_active=lambda: False,
            schedule_once=lambda delay_ms, callback: scheduled.append((delay_ms, callback)),
        )

        rule_a = MoveRule("walk_right", "horizontal", 130)
        rule_b = MoveRule("walk_left", "horizontal", 130)
        controller._start_move(rule_a)
        a_start_callback = scheduled[-1][1]

        controller.interrupt()
        a_end_callback = scheduled[-1][1]

        controller._start_move(rule_b)
        b_start_callback = scheduled[-1][1]

        self.assertEqual(director.started, ["walk_right", "walk_left"])
        self.assertEqual(director.ended, 1)

        a_end_callback()
        self.assertEqual(single_switch.started, 0)
        self.assertEqual(mode_switch.started, 0)

        a_start_callback()
        self.assertFalse(controller._move_timer.isActive())
        self.assertEqual(window.moves, [])

        b_start_callback()
        self.assertTrue(controller._move_timer.isActive())

        controller.shutdown()


if __name__ == "__main__":
    unittest.main()

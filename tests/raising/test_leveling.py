from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.raising.leveling import (
    apply_level_ups,
    exp_to_next_level,
    required_exp_for_level,
)
from core.raising.pet_state import PetState


class LevelingSmokeTest(unittest.TestCase):
    def test_no_level_up_keeps_exp_as_progress_to_next_level(self) -> None:
        state = PetState(level=1, exp=39)

        result = apply_level_ups(state)

        self.assertFalse(result.leveled)
        self.assertEqual(state.level, 1)
        self.assertEqual(state.exp, 39)
        self.assertEqual(exp_to_next_level(state), 1)

    def test_single_level_up_consumes_required_exp_and_applies_rewards(self) -> None:
        state = PetState(level=1, exp=40, mood=80, energy=70, health=90)

        result = apply_level_ups(state)

        self.assertTrue(result.leveled)
        self.assertEqual(result.levels_gained, 1)
        self.assertEqual(state.level, 2)
        self.assertEqual(state.exp, 0)
        self.assertEqual(state.money, 10)
        self.assertEqual(state.affection, 1)
        self.assertEqual(state.mood, 83)
        self.assertEqual(state.energy, 72)
        self.assertEqual(state.health, 91)

    def test_multi_level_up_repeats_until_exp_is_below_next_threshold(self) -> None:
        state = PetState(
            level=1,
            exp=required_exp_for_level(1) + required_exp_for_level(2) + 5,
            mood=70,
            energy=70,
            health=70,
        )

        result = apply_level_ups(state)

        self.assertTrue(result.leveled)
        self.assertEqual(result.levels_gained, 2)
        self.assertEqual(state.level, 3)
        self.assertEqual(state.exp, 5)
        self.assertEqual(result.consumed_exp, 100)
        self.assertEqual(exp_to_next_level(state), 75)
        self.assertEqual(state.money, 20)
        self.assertEqual(state.affection, 2)

    def test_loaded_level_cannot_drop_below_one(self) -> None:
        state = PetState(level=0, exp=0)

        self.assertEqual(state.level, 1)


if __name__ == "__main__":
    unittest.main()

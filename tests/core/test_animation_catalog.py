from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from core.playback.catalog import ActionSpec, AnimationCatalog
from core.playback.clip import Clip


def _clip(name: str) -> Clip:
    return Clip(
        frame_paths=(Path(f"{name}_000_125.png"),),
        frame_intervals_ms=(125,),
    )


class AnimationCatalogVariantTest(unittest.TestCase):
    def test_phased_stage_variants_are_not_tied_to_loop_variant(self) -> None:
        catalog = AnimationCatalog(
            {
                "raise": {
                    "normal": {
                        "loop": {
                            "01": {"main": _clip("loop_01")},
                        },
                        "start": {
                            "01": {"main": _clip("start_01")},
                            "02": {"main": _clip("start_02")},
                        },
                        "end": {
                            "01": {"main": _clip("end_01")},
                            "02": {"main": _clip("end_02")},
                        },
                    }
                }
            },
            {"raise": ActionSpec(id="raise", title="提起", type="phased")},
        )

        with patch(
            "core.playback.catalog.random.choice",
            side_effect=lambda variants: variants[-1],
        ):
            mode = catalog.mode_for("raise", "normal", action_type="phased")

        self.assertEqual(mode.loop_variant, "01")
        self.assertEqual(mode.start_variant, "02")
        self.assertEqual(mode.end_variant, "02")


if __name__ == "__main__":
    unittest.main()

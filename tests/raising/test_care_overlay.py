from __future__ import annotations

import unittest

from core.raising.care_overlay import config_for_action_state


class CareOverlayConfigTest(unittest.TestCase):
    def test_action_config_is_complete_and_direct(self) -> None:
        config = config_for_action_state(
            {
                "item_icon_size_ratio": 0.99,
                "actions": {
                    "eat": {
                        "ill": {
                            "item_icon_size_ratio": 0.16,
                            "item_icon_center_x_ratio": 0.5,
                            "item_icon_center_y_ratio": 0.62,
                            "item_icon_visible_start_ratio": 0.2,
                            "item_icon_visible_end_ratio": 0.85,
                            "item_icon_opacity": 1.0,
                            "item_icon_layer": "behind_front",
                            "item_icon_background_enabled": False,
                        }
                    }
                },
            },
            "eat",
            "ill",
        )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.size_ratio, 0.16)
        self.assertEqual(config.center_y_ratio, 0.62)
        self.assertEqual(config.layer, "behind_front")
        self.assertFalse(config.background_enabled)

    def test_missing_state_config_disables_overlay_for_that_state(self) -> None:
        config = config_for_action_state(
            {
                "actions": {
                    "eat": {
                        "normal": {
                            "item_icon_size_ratio": 0.16,
                            "item_icon_center_x_ratio": 0.5,
                            "item_icon_center_y_ratio": 0.45,
                            "item_icon_visible_start_ratio": 0.2,
                            "item_icon_visible_end_ratio": 0.85,
                            "item_icon_opacity": 1.0,
                            "item_icon_layer": "behind_front",
                            "item_icon_background_enabled": False,
                        }
                    }
                },
            },
            "eat",
            "ill",
        )

        self.assertIsNone(config)


if __name__ == "__main__":
    unittest.main()

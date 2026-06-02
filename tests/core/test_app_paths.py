from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import app_paths


class AppPathSmokeTest(unittest.TestCase):
    def test_project_root_save_location_uses_root_saves_in_dev(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            config = tmp / "app_settings.json"
            config.write_text(
                json.dumps({"save_location": "project_root"}),
                encoding="utf-8",
            )
            root = tmp / "project"
            support = tmp / "support"

            with (
                patch.object(app_paths, "config_path", return_value=config),
                patch.object(app_paths, "resource_root", return_value=root),
                patch.object(app_paths, "app_support_dir", return_value=support),
                patch.object(app_paths, "is_frozen", return_value=False),
            ):
                path = app_paths.save_game_path()

        self.assertEqual(path, root / "saves" / "savegame.json")

    def test_app_support_save_location_uses_app_support_saves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            config = tmp / "app_settings.json"
            config.write_text(
                json.dumps({"save_location": "app_support"}),
                encoding="utf-8",
            )
            root = tmp / "project"
            support = tmp / "support"

            with (
                patch.object(app_paths, "config_path", return_value=config),
                patch.object(app_paths, "resource_root", return_value=root),
                patch.object(app_paths, "app_support_dir", return_value=support),
                patch.object(app_paths, "is_frozen", return_value=False),
            ):
                path = app_paths.save_game_path()

        self.assertEqual(path, support / "saves" / "savegame.json")

    def test_project_root_save_location_falls_back_to_app_support_when_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            config = tmp / "app_settings.json"
            config.write_text(
                json.dumps({"save_location": "project_root"}),
                encoding="utf-8",
            )
            root = tmp / "project"
            support = tmp / "support"

            with (
                patch.object(app_paths, "config_path", return_value=config),
                patch.object(app_paths, "resource_root", return_value=root),
                patch.object(app_paths, "app_support_dir", return_value=support),
                patch.object(app_paths, "is_frozen", return_value=True),
            ):
                path = app_paths.save_game_path()

        self.assertEqual(path, support / "saves" / "savegame.json")

    def test_missing_app_settings_uses_app_support_saves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            config = tmp / "missing.json"
            root = tmp / "project"
            support = tmp / "support"

            with (
                patch.object(app_paths, "config_path", return_value=config),
                patch.object(app_paths, "resource_root", return_value=root),
                patch.object(app_paths, "app_support_dir", return_value=support),
                patch.object(app_paths, "is_frozen", return_value=False),
            ):
                path = app_paths.save_game_path()

        self.assertEqual(path, support / "saves" / "savegame.json")


if __name__ == "__main__":
    unittest.main()

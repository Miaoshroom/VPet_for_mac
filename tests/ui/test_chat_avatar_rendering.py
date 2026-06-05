from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from ui.chat.avatar import clear_avatar_cache, render_avatar_pixmap


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class ChatAvatarRenderingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _app()
        clear_avatar_cache()

    def test_avatar_renderer_outputs_high_dpi_round_pixmap_without_pet_window(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "avatar.png"
            image = QImage(96, 64, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(36, 120, 210))
            self.assertTrue(image.save(str(source_path)))

            pixmap = render_avatar_pixmap(
                source_path,
                28,
                device_pixel_ratio=2.0,
                fallback_id="chatAvatarUser",
            )

        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 56)
        self.assertEqual(pixmap.height(), 56)
        self.assertAlmostEqual(pixmap.devicePixelRatio(), 2.0)
        self.assertEqual(round(pixmap.width() / pixmap.devicePixelRatio()), 28)

        result = pixmap.toImage()
        self.assertEqual(result.pixelColor(0, 0).alpha(), 0)
        self.assertGreater(result.pixelColor(28, 28).alpha(), 0)

    def test_missing_avatar_uses_high_dpi_fallback(self) -> None:
        pixmap = render_avatar_pixmap(
            Path("/missing/avatar.png"),
            28,
            device_pixel_ratio=2.0,
            fallback_id="chatAvatarPet",
        )

        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 56)
        self.assertEqual(pixmap.height(), 56)
        self.assertAlmostEqual(pixmap.devicePixelRatio(), 2.0)


if __name__ == "__main__":
    unittest.main()

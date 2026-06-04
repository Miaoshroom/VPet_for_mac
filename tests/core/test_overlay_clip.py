from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from core.playback.clip import Clip
from core.playback.overlay_clip import (
    PixmapOverlayClip,
    PixmapOverlayConfig,
    clip_with_pixmap_overlay,
)

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    instance = QApplication.instance()
    if instance is not None:
        return instance
    _APP = QApplication([])
    return _APP


def _clip() -> Clip:
    return Clip(
        frame_paths=(Path("frame_000_125.png"),),
        frame_intervals_ms=(125,),
        action_id="eat",
        source_state="normal",
        phase="single",
        variant="01",
    )


class PixmapOverlayClipTest(unittest.TestCase):
    def test_null_overlay_returns_base_clip(self) -> None:
        _app()
        base = _clip()

        wrapped = clip_with_pixmap_overlay(base, QPixmap(), PixmapOverlayConfig())

        self.assertIs(wrapped, base)

    def test_overlay_clip_keeps_debug_metadata(self) -> None:
        _app()
        overlay = QPixmap(8, 8)
        base = _clip()

        wrapped = clip_with_pixmap_overlay(base, overlay, PixmapOverlayConfig())

        self.assertIsInstance(wrapped, PixmapOverlayClip)
        self.assertEqual(wrapped.action_id, "eat")
        self.assertEqual(wrapped.source_state, "normal")
        self.assertEqual(wrapped.phase, "single")
        self.assertEqual(wrapped.variant, "01")


if __name__ == "__main__":
    unittest.main()

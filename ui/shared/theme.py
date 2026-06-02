"""Qt 主题设置"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import QApplication


def apply_app_theme(app: QApplication) -> None:
    cache_dir = Path(tempfile.gettempdir()) / "VPet_for_mac" / "qdarktheme-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))

    try:
        import qdarktheme
        import qdarktheme._template.filter as qdarktheme_filter
    except ImportError:
        return

    def cache_root(version: str) -> Path:
        path = cache_dir / "qdarktheme" / f"v{version}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    qdarktheme_filter.get_cash_root_path = cache_root

    try:
        qdarktheme.setup_theme("auto", corner_shape="rounded", default_theme="light")
    except Exception:
        app.setStyleSheet("")

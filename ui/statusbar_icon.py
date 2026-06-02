"""状态栏图标"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def create_statusbar_icon(
    app: QApplication,
    icon_path: Path,
    on_quit: Callable[[], None],
    build_menu: Callable[[QMenu], None] | None = None,
) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(QIcon(str(icon_path)), app)
    tray.setToolTip("喵喵x")

    menu = QMenu()
    if build_menu is None:
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(on_quit)
    else:
        def rebuild_menu() -> None:
            menu.clear()
            build_menu(menu)

        menu.aboutToShow.connect(rebuild_menu)
        rebuild_menu()
    tray.setContextMenu(menu)
    tray.show()
    return tray

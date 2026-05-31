"""桌宠配置编辑器入口：独立进程运行，也可通过桌宠右键菜单启动"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

# 确保父目录在 sys.path 中，使 editor.* 导入和 core.* 导入都能正常工作
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from editor.window import EditorWindow

APP_ICON = _ROOT / "resources" / "app_icon.png"


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    win = EditorWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

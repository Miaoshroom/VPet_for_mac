"""编辑器壳：QTabWidget 容器 + 保存，不管各 tab 内部逻辑"""
from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QMessageBox

from editor.tabs.actions import ActionsTab
from editor.tabs.asset_prep import AssetPrepTab
from editor.tabs.assets import AssetsTab
from editor.tabs.behavior import BehaviorTab
from editor.tabs.plugins import PluginsTab


class EditorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("桌宠编辑器")
        self.resize(960, 680)

        self._tabs = QTabWidget(self)
        self.setCentralWidget(self._tabs)

        self._tabs.addTab(AssetPrepTab(self), "素材配制")
        self._tabs.addTab(AssetsTab(self), "动作素材")
        self._tabs.addTab(ActionsTab(self), "动作注册")
        self._tabs.addTab(BehaviorTab(self), "自动行为")
        self._tabs.addTab(PluginsTab(self), "插件开关")

        save_action = QAction("保存", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_current)
        self.menuBar().addAction(save_action)

    def _save_current(self) -> None:
        tab = self._tabs.currentWidget()
        if not hasattr(tab, "save"):
            return
        try:
            tab.save()
            QMessageBox.information(self, "保存", "保存成功。请重启桌宠以生效。")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

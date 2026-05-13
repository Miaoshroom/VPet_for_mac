"""
示例

插件命名规则：
- 插件名写在 config/plugin_loader.json 里，例如：show_sticker，写在这里的插件会被加载x
- 插件文件路径同名，例如：plugins/show_sticker.py
- 插件类名使用大驼峰 + Plugin，比如：ShowStickerPlugin

plugin_loader会自动推导：
show_sticker -> import plugins.show_sticker -> 找 ShowStickerPlugin

复制这个文件时，只需要改：
- 文件名
- 类名
- PLUGIN_NAME
- MENU_TITLE
"""

from __future__ import annotations


class ExamplePlugin:
    PLUGIN_NAME = "example"
    MENU_TITLE = "示例"

    def __init__(self, context) -> None:
        self._app = context["app"]
        self._window = context["window"]
        self._enabled = False

    def menu_title(self) -> str:
        return self.MENU_TITLE

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if enabled:
            self.start()
        else:
            self.shutdown()

    def start(self) -> None:
        if not self._enabled:
            return
        # 从这里开始插件逻辑

    def shutdown(self) -> None:
        # 从这里停止插件逻辑
        pass

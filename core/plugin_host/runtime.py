"""插件运行时协调"""

from __future__ import annotations


class PluginRuntime:
    def __init__(self) -> None:
        # 当前占用动作控制权的插件
        self._action_owner: str | None = None
        # 预留以后做优先级，先不用这个
        self._priority = 0

    def try_begin_action(self, plugin_name: str, priority: int = 0) -> bool:
        # 先到先得，已有 owner 时其他插件不能抢
        if self._action_owner is not None and self._action_owner != plugin_name:
            return False
        self._action_owner = plugin_name
        self._priority = priority
        return True

    def end_action(self, plugin_name: str) -> None:
        # 只有 owner 插件本人才能释放锁，避免其他插件误关
        if self._action_owner == plugin_name:
            self._action_owner = None
            self._priority = 0

    def action_active(self) -> bool:
        # core中的自动动作通过这个判断是否需要避让插件
        return self._action_owner is not None

    def action_owner(self) -> str | None:
        return self._action_owner

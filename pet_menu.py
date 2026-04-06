"""右键菜单"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QWidget, QMenu


def show_pet_menu(
    parent: QWidget,
    global_pos: QPoint,
    on_zoom_in: Callable[[], None],  #放大/缩小回调函数
    on_zoom_out: Callable[[], None],
    state_handlers: dict[str, Callable[[], None]],  # 生成动态状态列表
    current_state_title: str | None,
    on_set_start_pos: Callable[[], None],  #设置启动位置回调
    on_quit: Callable[[], None],  #退出程序
) -> None:

    menu = QMenu(parent)

    zoom_in = menu.addAction("放大 (+30)")
    zoom_out = menu.addAction("缩小 (-30)")
    switch_menu = menu.addMenu("切换状态")
    action_map = {}
    for title, handler in state_handlers.items():
        action = switch_menu.addAction(title)
        action.setCheckable(True)
        action.setChecked(title == current_state_title)
        action_map[action] = handler
    set_start_pos = menu.addAction("设置启动位置")
    menu.addSeparator()
    quit_action = menu.addAction("退出")

    chosen = menu.exec(global_pos)
    if chosen is zoom_in:
        on_zoom_in()
    elif chosen is zoom_out:
        on_zoom_out()
    elif chosen in action_map:
        action_map[chosen]()
    elif chosen is set_start_pos:
        on_set_start_pos()
    elif chosen is quit_action:
        on_quit()

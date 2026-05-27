"""启动与关闭时的 single 动画流程"""

from __future__ import annotations

import random

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from core.animation import Clip, Mode, PetAnimationDirector
from core.playback.catalog import AnimationCatalog
from core.single_autoswitch import SingleAutoSwitch
from core.single_player import SinglePlayer


def pick_single_clip_for_state(
    config_ids: tuple[str, ...],
    *,
    animation_catalog: AnimationCatalog,
    pet_state: str,
) -> Clip | None:
    if not config_ids:
        return None
    # 启动和关闭 single 也按当前状态挑 没素材就跳过
    candidates = [
        mode_id
        for mode_id in config_ids
        if animation_catalog.is_single_available(mode_id, pet_state)
    ]
    if not candidates:
        return None
    return animation_catalog.single_for(random.choice(candidates), pet_state)


def pick_startup(
    default_mode: Mode,
    startup_ids: tuple[str, ...],
    *,
    animation_catalog: AnimationCatalog,
    pet_state: str,
) -> tuple[Clip | None, QPixmap]:
    """选择启动 single，并返回窗口初始显示的首帧。"""

    default_clip = default_mode.start if default_mode.is_phased else default_mode.loop
    assert default_clip is not None
    startup_clip = pick_single_clip_for_state(
        startup_ids,
        animation_catalog=animation_catalog,
        pet_state=pet_state,
    )
    initial_pixmap = startup_clip.frame(0) if startup_clip is not None else default_clip.frame(0)
    return startup_clip, initial_pixmap


def play_startup(
    window,
    director: PetAnimationDirector,
    single_autoswitch: SingleAutoSwitch,
    single_player: SinglePlayer,
    startup_clip: Clip | None,
) -> None:
    """启动时先播 single，播完后再进入默认 mode。"""

    def start_default_mode() -> None:
        director.start_default_mode()
        single_autoswitch.start()

    if startup_clip is None:
        start_default_mode()
        return

    def play_clip() -> None:
        if not single_player.play(startup_clip, on_finished=start_default_mode, resume=False):
            start_default_mode()

    QTimer.singleShot(0, play_clip)


def build_shutdown_handler(
    app: QApplication,
    window,
    badge,
    director: PetAnimationDirector,
    single_autoswitch: SingleAutoSwitch,
    single_player: SinglePlayer,
    mode_autoswitch_timer,
    shutdown_ids: tuple[str, ...],
    animation_catalog: AnimationCatalog,
    shutdown_hooks=(),
):
    """构建菜单退出回调：如有配置则先播 shutdown single。"""

    is_shutting_down = False

    def request_shutdown() -> None:
        nonlocal is_shutting_down
        if is_shutting_down:
            return
        is_shutting_down = True
        badge.hide()
        single_autoswitch.stop()
        if mode_autoswitch_timer is not None:
            mode_autoswitch_timer.stop()
        for hook in shutdown_hooks:
            hook()
        director.stop()

        shutdown_clip = pick_single_clip_for_state(
            shutdown_ids,
            animation_catalog=animation_catalog,
            pet_state=director.pet_state(),
        )
        if shutdown_clip is None:
            app.quit()
            return
        if not single_player.play(
            shutdown_clip,
            on_finished=app.quit,
            resume=False,
        ):
            app.quit()

    return request_shutdown

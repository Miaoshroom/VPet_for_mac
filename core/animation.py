"""动画加载与调度"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap


def load_numbered_pngs(folder: Path) -> list[QPixmap]:
    """
    按顺序加载文件夹中的帧动画图片，一旦缺号或文件无效就break
    返回：QPixmap 列表（动画帧）
    """
    frames: list[QPixmap] = []
    i = 0
    while True:
        path = folder / f"{i}.png"
        if not path.is_file():
            break
        pix = QPixmap(str(path))
        if pix.isNull():
            break
        frames.append(pix)
        i += 1
    return frames


@dataclass(frozen=True)
class Clip:
    """一个动画 = 多帧 + 播放速度"""

    frames: list[QPixmap]
    interval_ms: int

    def __post_init__(self) -> None:  # 动画必须合法
        if self.interval_ms < 1:  # 贞间隔必须大于1
            raise ValueError("帧间隔必须大于1")
        if not self.frames:  # 必须至少有一帧
            raise ValueError("必须至少有一帧")


@dataclass(frozen=True)
class Mode:
    """一个可切换模式，支持普通循环或 start-loop-end 分段"""

    loop: Clip
    start: Clip | None = None
    end: Clip | None = None

    def __post_init__(self) -> None:
        has_start = self.start is not None
        has_end = self.end is not None
        if has_start != has_end:
            raise ValueError("分段模式必须同时提供 start 和 end")

    @property
    def is_phased(self) -> bool:
        return self.start is not None


class FlipbookPlayer(QObject):
    """
    逐帧动画播放器
    功能：
    - 按时间播放帧（QTimer驱动）
    - 支持循环或单次播放
    - 通过信号输出当前帧
    """

    frame_changed = pyqtSignal(object)  # QPixmap
    finished = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)
        self._frames: list[QPixmap] = []
        self._index = 0
        self._loop = False

    def is_playing(self) -> bool:
        return self._timer.isActive()

    def disconnect_finished(self) -> None:
        try:
            self.finished.disconnect()
        except TypeError:
            pass

    def stop(self) -> None:
        self._timer.stop()

    def _on_tick(self) -> None:
        if not self._frames:
            return
        self.frame_changed.emit(self._frames[self._index])
        self._index += 1
        if self._index < len(self._frames):
            return
        if self._loop:
            self._index = 0
            return
        self._timer.stop()
        self.finished.emit()

    def play(self, clip: Clip, *, loop: bool) -> None:
        self.stop()
        self._frames = clip.frames
        self._loop = loop
        self._index = 0
        if not self._frames:
            self.finished.emit()
            return
        self.frame_changed.emit(self._frames[0])
        if len(self._frames) == 1 and not loop:
            self.finished.emit()
            return
        self._index = 1 if len(self._frames) > 1 else 0
        self._timer.start(clip.interval_ms)


class PressHoldAnimator(QObject):
    """按住动画"""

    frame_changed = pyqtSignal(object)

    def __init__(self, start: Clip, loop: Clip, end: Clip, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._start_c = start
        self._loop_c = loop
        self._end_c = end
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(self.frame_changed)
        self._on_resume: Callable[[], None] | None = None
        self._wants_end = False
        self._phase = "idle"

    def start(self, on_resume: Callable[[], None] | None = None) -> None:
        self._player.stop()
        self._player.disconnect_finished()
        self._on_resume = on_resume
        self._wants_end = False
        self._phase = "start"
        self._player.finished.connect(self._after_start)
        self._player.play(self._start_c, loop=False)

    def end(self) -> None:
        if self._phase in ("end", "idle"):
            return
        self._wants_end = True
        if self._phase == "loop":
            self._play_end()

    def stop(self) -> None:
        self._player.stop()
        self._player.disconnect_finished()
        self._on_resume = None
        self._wants_end = False
        self._phase = "idle"

    def is_active(self) -> bool:
        return self._phase != "idle"

    def _after_start(self) -> None:
        self._player.disconnect_finished()
        if self._wants_end:
            self._play_end()
            return
        self._phase = "loop"
        self._player.play(self._loop_c, loop=True)

    def _play_end(self) -> None:
        self._phase = "end"
        self._player.stop()
        self._player.disconnect_finished()
        self._player.finished.connect(self._to_idle)
        self._player.play(self._end_c, loop=False)

    def _to_idle(self) -> None:
        self._player.disconnect_finished()
        self._phase = "idle"
        self._wants_end = False
        cb = self._on_resume
        self._on_resume = None
        if cb:
            cb()


class PetAnimationDirector(QObject):
    """总调度"""

    frame_changed = pyqtSignal(object)

    def __init__(
        self,
        modes: dict[str, Mode],
        default_mode: str,
        interactions: dict[str, PressHoldAnimator],
        default_interaction: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not modes:
            raise ValueError("必须至少提供一个可切换模式")
        if default_mode not in modes:
            raise ValueError(f"默认模式不存在: {default_mode}")
        if default_interaction not in interactions:
            raise ValueError(f"默认互动不存在: {default_interaction}")
        self._modes = modes
        self._default_mode = default_mode
        self._current_mode = default_mode
        self._pending_mode: str | None = None
        self._phase = "idle"
        self._interactions = interactions
        self._default_interaction = default_interaction
        self._active_interaction_name: str | None = None
        self._mode_player = FlipbookPlayer(self)
        self._mode_player.frame_changed.connect(self.frame_changed)
        for interaction in self._interactions.values():
            interaction.frame_changed.connect(self.frame_changed)

    def current_mode_name(self) -> str:
        return self._pending_mode or self._current_mode

    def current_mode(self) -> Mode:
        return self._modes[self._current_mode]

    def is_press_active(self) -> bool:
        return self.is_interaction_active()

    def is_interaction_active(self) -> bool:
        return self._active_interaction_name is not None

    def start_default_mode(self) -> None:
        self._start_mode(self._default_mode)

    def switch_mode(self, mode_name: str) -> None:
        if mode_name not in self._modes:
            raise KeyError(f"未知模式: {mode_name}")
        if mode_name == self.current_mode_name():
            return
        if self.is_interaction_active():
            self._current_mode = mode_name
            self._pending_mode = None
            return

        mode = self.current_mode()
        if mode.is_phased:
            self._pending_mode = mode_name
            if self._phase == "loop":
                self._play_current_end()
            return
        self._start_mode(mode_name)

    def on_mouse_press(self) -> None:
        self.start_interaction(self._default_interaction)

    def on_mouse_release(self) -> None:
        self.end_interaction()

    def start_interaction(self, interaction_name: str) -> None:
        if interaction_name not in self._interactions:
            raise KeyError(f"未知互动: {interaction_name}")
        if self.is_interaction_active():
            return
        self._stop_mode_player()
        self._pending_mode = None
        self._active_interaction_name = interaction_name
        self._interactions[interaction_name].start(on_resume=self._resume_current_mode)

    def end_interaction(self) -> None:
        if self._active_interaction_name is None:
            return
        self._interactions[self._active_interaction_name].end()

    def _stop_mode_player(self) -> None:
        self._mode_player.stop()
        self._mode_player.disconnect_finished()

    def _start_mode(self, mode_name: str) -> None:
        self._stop_mode_player()
        self._current_mode = mode_name
        self._pending_mode = None
        mode = self.current_mode()
        if mode.is_phased:
            self._phase = "start"
            self._mode_player.finished.connect(self._after_mode_start)
            self._mode_player.play(mode.start, loop=False)
            return
        self._phase = "loop"
        self._mode_player.play(mode.loop, loop=True)

    def _resume_current_mode(self) -> None:
        self._stop_mode_player()
        self._active_interaction_name = None
        self._pending_mode = None
        self._phase = "loop"
        self._mode_player.play(self.current_mode().loop, loop=True)

    def _after_mode_start(self) -> None:
        self._mode_player.disconnect_finished()
        if self._pending_mode is not None:
            self._play_current_end()
            return
        self._phase = "loop"
        self._mode_player.play(self.current_mode().loop, loop=True)

    def _play_current_end(self) -> None:
        mode = self.current_mode()
        if not mode.is_phased:
            next_mode = self._pending_mode
            self._pending_mode = None
            if next_mode is not None:
                self._start_mode(next_mode)
            return
        self._stop_mode_player()
        self._phase = "end"
        self._mode_player.finished.connect(self._after_mode_end)
        self._mode_player.play(mode.end, loop=False)

    def _after_mode_end(self) -> None:
        self._mode_player.disconnect_finished()
        next_mode = self._pending_mode
        if next_mode is None:
            self._resume_current_mode()
            return
        self._start_mode(next_mode)

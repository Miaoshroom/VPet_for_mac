"""单循环动画+sle动画"""

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


class SingleAnimator(QObject):
    """单次动画播放器，播完回idle"""

    frame_changed = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(self.frame_changed)
        self._on_complete: Callable[[], None] | None = None

    def play(self, clip: Clip, on_complete: Callable[[], None] | None = None) -> None:
        self._player.stop()
        self._on_complete = on_complete
        self._player.disconnect_finished()
        self._player.finished.connect(self._handle_finished)
        self._player.play(clip, loop=False)

    def stop(self) -> None:
        self._player.stop()
        self._on_complete = None

    def _handle_finished(self) -> None:
        cb = self._on_complete
        self._on_complete = None
        if cb:
            cb()


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
        self._on_idle: Callable[[], None] | None = None
        self._wants_end = False
        self._phase = "idle"

    def start(self, on_idle: Callable[[], None] | None = None) -> None:
        self._player.stop()
        self._player.disconnect_finished()
        self._on_idle = on_idle
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
        self._on_idle = None
        self._wants_end = False
        self._phase = "idle"

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
        cb = self._on_idle
        self._on_idle = None
        if cb:
            cb()


class PetAnimationDirector(QObject):
    """总调度"""

    frame_changed = pyqtSignal(object)

    def __init__(
        self,
        idle: Clip,
        press: PressHoldAnimator,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._idle_clip = idle
        self._press = press
        self._idle_player = FlipbookPlayer(self)
        self._idle_player.frame_changed.connect(self.frame_changed)
        self._single = SingleAnimator(self)
        self._single.frame_changed.connect(self.frame_changed)

        self._press.frame_changed.connect(self.frame_changed)

    def start_idle(self) -> None:  # 播放idle
        self._press.stop()
        self._single.stop()
        self._idle_player.stop()
        self._idle_player.play(self._idle_clip, loop=True)

    def on_mouse_press(self) -> None:
        self._idle_player.stop()
        self._single.stop()
        self._press.start(on_idle=self.start_idle)

    def on_mouse_release(self) -> None:
        self._press.end()

    def play_single(self, clip: Clip) -> None:  # 播放单个动画
        self._idle_player.stop()
        self._press.stop()
        self._single.stop()
        self._single.play(clip, on_complete=self.start_idle)

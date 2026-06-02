"""播放一次 single 动画并恢复当前 mode。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal

from core.animation import Clip, FlipbookPlayer, PetAnimationDirector
from core.playback.catalog import AnimationCatalog
from core.playback.director import PlaybackDebugSnapshot


@dataclass
class _SingleRun:
    clip: Clip
    resume_mode: str | None
    on_finished: Callable[[], None] | None
    interruptible: bool


class SinglePlayer(QObject):
    finished = pyqtSignal()

    def __init__(
        self,
        parent: QObject,
        director: PetAnimationDirector,
        window,
        *,
        animation_catalog: AnimationCatalog | None = None,
    ) -> None:
        super().__init__(parent)
        self._director = director
        self._window = window
        self._animation_catalog = animation_catalog
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(window.set_pixmap)
        self._player.finished.connect(self._finish)
        self._current: _SingleRun | None = None
        self._paused: _SingleRun | None = None
        self._visual_override_active = False

    def is_active(self) -> bool:
        return self._current is not None

    def is_paused(self) -> bool:
        return self._paused is not None

    def blocks_interaction(self) -> bool:
        return self._current is not None and not self._current.interruptible

    def play(
        self,
        clip: Clip,
        on_finished: Callable[[], None] | None = None,
        *,
        resume: bool = True,  # 专门给启动和退出动画用的
        interruptible: bool = False,
    ) -> bool:
        if self._current is not None:
            return False
        resume_mode = self._director.current_mode_name() if resume else None
        self._current = _SingleRun(clip, resume_mode, on_finished, interruptible)
        self._begin_visual_override()
        self._director.stop()
        self._player.play(clip, loop=False)
        return True

    def pause(self) -> bool:
        if self._current is None or not self._current.interruptible:
            return False
        self._paused = self._current
        self._current = None
        self._player.stop()
        self._end_visual_override()
        return True

    def resume(self) -> bool:
        if self._current is not None or self._paused is None:
            return False
        self._current = self._paused
        self._paused = None
        self._begin_visual_override()
        self._director.stop()
        self._player.play(self._current.clip, loop=False)
        return True

    def stop(self) -> None:
        self._player.stop()
        self._current = None
        self._paused = None
        self._end_visual_override()

    def replay_current_action(self) -> bool:
        if self._current is None:
            return False
        self._player.play(self._current.clip, loop=False)
        return True

    def debug_snapshot(self) -> PlaybackDebugSnapshot | None:
        if self._current is None:
            return None
        frame = self._player.debug_info()
        clip = self._current.clip
        action_id = clip.action_id
        return PlaybackDebugSnapshot(
            source="single",
            action_id=action_id,
            action_title=self._action_title(action_id),
            phase=clip.phase or "single",
            pet_state=self._director.pet_state(),
            source_state=clip.source_state,
            variant=clip.variant,
            frame_index=frame.frame_index if frame is not None else None,
            frame_count=frame.frame_count if frame is not None else len(clip),
            frame_path=frame.frame_path if frame is not None else clip.frame_paths[0],
        )

    def _finish(self) -> None:
        current = self._current
        if current is None:
            return
        self._current = None
        self._end_visual_override()
        if current.resume_mode is not None:
            resume_mode = self._director.current_mode_name()
            if self._director.is_mode_available(resume_mode):
                self._director.resume_mode(resume_mode)
            else:
                self._director.start_default_mode()
        if current.on_finished is not None:
            current.on_finished()
        self.finished.emit()

    def _begin_visual_override(self) -> None:
        if self._visual_override_active:
            return
        self._director.begin_visual_override()
        self._visual_override_active = True

    def _end_visual_override(self) -> None:
        if not self._visual_override_active:
            return
        self._director.end_visual_override()
        self._visual_override_active = False

    def _action_title(self, action_id: str | None) -> str | None:
        if action_id is None:
            return None
        if self._animation_catalog is None:
            return action_id
        try:
            return self._animation_catalog.action_title(action_id)
        except KeyError:
            return action_id

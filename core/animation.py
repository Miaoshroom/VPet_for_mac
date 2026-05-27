"""播放模块兼容导出

运行时动画逻辑位于 core.playback.*。此模块只保留给迁移期旧导入使用。
"""

from core.playback import (
    ActionSpec,
    AnimationCatalog,
    Clip,
    FlipbookPlayer,
    Mode,
    PetAnimationDirector,
    PhasedSequencePlayer,
    PressHoldAnimator,
)

__all__ = [
    "ActionSpec",
    "AnimationCatalog",
    "Clip",
    "FlipbookPlayer",
    "Mode",
    "PetAnimationDirector",
    "PhasedSequencePlayer",
    "PressHoldAnimator",
]

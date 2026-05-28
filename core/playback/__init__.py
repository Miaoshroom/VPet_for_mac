"""新动画素材目录的播放基础类型"""

from core.playback.catalog import (
    DEFAULT_PET_STATE,
    LAYERS,
    MATERIAL_STATES,
    PET_STATES,
    PHASES,
    ActionSpec,
    AnimationCatalog,
    validate_pet_state,
)
from core.playback.clip import Clip, Mode, parse_frame_filename
from core.playback.director import PlaybackDebugSnapshot, PetAnimationDirector, PressHoldAnimator
from core.playback.flipbook import FlipbookDebugInfo, FlipbookPlayer
from core.playback.phased_player_general import PhasedSequencePlayer

__all__ = [
    "ActionSpec",
    "AnimationCatalog",
    "Clip",
    "DEFAULT_PET_STATE",
    "FlipbookPlayer",
    "LAYERS",
    "MATERIAL_STATES",
    "Mode",
    "PET_STATES",
    "PHASES",
    "PlaybackDebugSnapshot",
    "PetAnimationDirector",
    "PhasedSequencePlayer",
    "PressHoldAnimator",
    "FlipbookDebugInfo",
    "parse_frame_filename",
    "validate_pet_state",
]

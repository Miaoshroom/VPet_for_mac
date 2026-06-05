"""聊天提供方和后续界面接入的协议边界"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, Sequence
from uuid import uuid4

from core.chat.models import (
    AIRequestPayload,
    EffectRequest,
    PetContextSnapshot,
    ProviderResult,
)


class ChatProvider(Protocol):
    def complete(self, payload: AIRequestPayload) -> ProviderResult:
        """返回一轮离线聊天的非流式回应"""


class ChatPetContextProvider(Protocol):
    def snapshot(self) -> PetContextSnapshot:
        """返回当前宠物和运行时状态的只读快照"""


class ChatEffectExecutor(Protocol):
    def execute(self, effects: Sequence[EffectRequest]) -> Sequence[str]:
        """后续窗口层效果执行边界 第一阶段不使用"""


class Clock(Protocol):
    def now(self) -> datetime:
        """返回当前时间"""


class IdGenerator(Protocol):
    def new_id(self, prefix: str = "") -> str:
        """返回聊天对象的唯一标识"""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UUIDGenerator:
    def new_id(self, prefix: str = "") -> str:
        value = uuid4().hex
        if prefix:
            return f"{prefix}_{value}"
        return value


__all__ = [
    "ChatEffectExecutor",
    "ChatPetContextProvider",
    "ChatProvider",
    "Clock",
    "IdGenerator",
    "SystemClock",
    "UUIDGenerator",
]

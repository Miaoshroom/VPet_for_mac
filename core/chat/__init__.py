"""VPet AI 对话系统的离线核心"""

from __future__ import annotations

from core.chat.config import ChatConfig, load_chat_config
from core.chat.models import (
    AIReplyV1,
    AIRequestPayload,
    ChatAttachment,
    ChatMessage,
    ChatTurnResult,
    EffectRequest,
    ParseResult,
    PetContextSnapshot,
    ProviderResult,
)
from core.chat.providers.deepseek import DeepSeekChatProvider
from core.chat.service import ChatService

__all__ = [
    "AIReplyV1",
    "AIRequestPayload",
    "ChatAttachment",
    "ChatConfig",
    "ChatMessage",
    "ChatService",
    "ChatTurnResult",
    "DeepSeekChatProvider",
    "EffectRequest",
    "ParseResult",
    "PetContextSnapshot",
    "ProviderResult",
    "load_chat_config",
]

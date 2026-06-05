"""聊天提供方实现"""

from __future__ import annotations

from core.chat.providers.deepseek import DeepSeekChatProvider
from core.chat.providers.fake import FakeChatProvider

__all__ = ["DeepSeekChatProvider", "FakeChatProvider"]

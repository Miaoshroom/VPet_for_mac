"""聊天核心的纯数据结构

本包刻意避开 Qt 和窗口层导入
PetState 在这里以普通字典表示 避免 AI 层修改真实养成状态
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

SCHEMA_VERSION = 1
VISUAL_STATES = ("happy", "normal", "poor_condition", "ill")
LEGACY_STICKER_TEXT_RE = re.compile(r"^\[贴纸:(?P<id>[^\]]+)\]\s*(?P<label>.*)$")


class ChatSender(str, Enum):
    USER = "user"
    LOLITH = "lolith"
    SYSTEM = "system"


class ChatMessageType(str, Enum):
    TEXT = "text"
    STICKER = "sticker"
    FILE = "file"
    MIXED = "mixed"
    SYSTEM_NOTICE = "system_notice"


class ChatMessageStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    PENDING = "pending"


class AttachmentType(str, Enum):
    IMAGE = "image"
    FILE = "file"


class AIIntent(str, Enum):
    CHAT = "chat"
    ACTION_REQUEST = "action_request"
    USE_ITEM_REQUEST = "use_item_request"
    FALLBACK = "fallback"


class EffectKind(str, Enum):
    ACTION = "action"
    USE_ITEM = "use_item"


@dataclass(slots=True, frozen=True)
class ChatAttachment:
    id: str
    type: AttachmentType = AttachmentType.FILE
    path: str | None = None
    mime_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "type": self.type.value,
            "path": self.path,
            "mime_type": self.mime_type,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChatAttachment":
        return cls(
            id=str(data.get("id", "")),
            type=_enum_value(data.get("type"), AttachmentType, AttachmentType.FILE),
            path=_optional_str(data.get("path")),
            mime_type=_optional_str(data.get("mime_type")),
            metadata=_dict_value(data.get("metadata")),
            schema_version=_int_value(data.get("schema_version"), SCHEMA_VERSION),
        )


@dataclass(slots=True, frozen=True)
class ChatMessage:
    id: str
    timestamp: str
    sender: ChatSender
    type: ChatMessageType = ChatMessageType.TEXT
    text: str = ""
    sticker_id: str | None = None
    attachments: tuple[ChatAttachment, ...] = ()
    status: ChatMessageStatus = ChatMessageStatus.SENT
    metadata: Mapping[str, Any] = field(default_factory=dict)
    action_id: str | None = None
    intent: AIIntent | None = None
    state_request: Mapping[str, Any] | None = None
    pet_state_snapshot: Mapping[str, Any] | None = None
    parse_warnings: tuple[str, ...] = ()
    provider: str | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "timestamp": self.timestamp,
            "sender": self.sender.value,
            "type": self.type.value,
            "text": self.text,
            "sticker_id": self.sticker_id,
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "status": self.status.value,
            "metadata": dict(self.metadata),
            "action_id": self.action_id,
            "intent": self.intent.value if self.intent else None,
            "state_request": dict(self.state_request) if self.state_request else None,
            "pet_state_snapshot": (
                dict(self.pet_state_snapshot) if self.pet_state_snapshot else None
            ),
            "parse_warnings": list(self.parse_warnings),
            "provider": self.provider,
        }

    def to_context_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "timestamp": self.timestamp,
            "sender": self.sender.value,
            "type": self.type.value,
            "text": self.text,
            "sticker_id": self.sticker_id,
            "status": self.status.value,
            "metadata": dict(self.metadata),
            "action_id": self.action_id,
            "intent": self.intent.value if self.intent else None,
        }
        if self.type == ChatMessageType.STICKER and self.sticker_id:
            payload["label"] = str(self.metadata.get("label") or self.text or "")
            raw_tags = self.metadata.get("tags", ())
            if isinstance(raw_tags, list | tuple):
                payload["tags"] = [str(tag) for tag in raw_tags if str(tag).strip()]
            else:
                payload["tags"] = []
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChatMessage":
        raw_attachments = data.get("attachments", ())
        attachments: list[ChatAttachment] = []
        if isinstance(raw_attachments, list):
            for item in raw_attachments:
                if isinstance(item, Mapping):
                    attachments.append(ChatAttachment.from_dict(item))
        message_type = _message_type_value(data.get("type"))
        text = str(data.get("text", "") or "")
        metadata = _dict_value(data.get("metadata"))
        sticker_id = _optional_str(data.get("sticker_id"))
        message_type, sticker_id, text, metadata = _normalize_legacy_sticker_message(
            message_type,
            sticker_id,
            text,
            metadata,
        )
        return cls(
            id=str(data.get("id", "")),
            timestamp=str(data.get("timestamp", "")),
            sender=_enum_value(data.get("sender"), ChatSender, ChatSender.SYSTEM),
            type=message_type,
            text=text,
            sticker_id=sticker_id,
            attachments=tuple(attachments),
            status=_enum_value(
                data.get("status"), ChatMessageStatus, ChatMessageStatus.SENT
            ),
            metadata=metadata,
            action_id=_optional_str(data.get("action_id")),
            intent=_optional_enum(data.get("intent"), AIIntent),
            state_request=_optional_dict(data.get("state_request")),
            pet_state_snapshot=_optional_dict(data.get("pet_state_snapshot")),
            parse_warnings=_str_tuple(data.get("parse_warnings")),
            provider=_optional_str(data.get("provider")),
            schema_version=_int_value(data.get("schema_version"), SCHEMA_VERSION),
        )


@dataclass(slots=True, frozen=True)
class PetContextSnapshot:
    pet_state: Mapping[str, Any] = field(default_factory=dict)
    runtime_state: Mapping[str, Any] = field(default_factory=dict)
    visual_state: str = "normal"
    inventory: tuple[Mapping[str, Any], ...] = ()
    active_activity: Mapping[str, Any] | str | None = None
    recent_ai_usage: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def normalized_visual_state(self) -> str:
        if self.visual_state in VISUAL_STATES:
            return self.visual_state
        return "normal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pet_state": dict(self.pet_state),
            "runtime_state": dict(self.runtime_state),
            "visual_state": self.normalized_visual_state(),
            "inventory": [dict(item) for item in self.inventory],
            "active_activity": self.active_activity,
            "recent_ai_usage": dict(self.recent_ai_usage),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True, frozen=True)
class AIRequestPayload:
    conversation_goal: str
    persona: Mapping[str, Any]
    user_profile: Mapping[str, Any]
    style_rules: tuple[str, ...]
    time_context: Mapping[str, Any]
    pet_state: Mapping[str, Any]
    runtime_state: Mapping[str, Any]
    visual_state: str
    inventory: tuple[Mapping[str, Any], ...]
    active_activity: Mapping[str, Any] | str | None
    recent_messages: tuple[Mapping[str, Any], ...]
    long_term_memory: Mapping[str, Any]
    available_stickers: tuple[Mapping[str, Any], ...]
    available_actions: tuple[Mapping[str, Any], ...]
    allowed_state_requests: tuple[str, ...]
    forbidden_requests: tuple[str, ...]
    recent_ai_usage: Mapping[str, Any]
    user_message: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "conversation_goal": self.conversation_goal,
            "persona": dict(self.persona),
            "user_profile": dict(self.user_profile),
            "style_rules": list(self.style_rules),
            "time_context": dict(self.time_context),
            "pet_state": dict(self.pet_state),
            "runtime_state": dict(self.runtime_state),
            "visual_state": self.visual_state,
            "inventory": [dict(item) for item in self.inventory],
            "active_activity": self.active_activity,
            "recent_messages": [dict(item) for item in self.recent_messages],
            "long_term_memory": dict(self.long_term_memory),
            "available_stickers": [dict(item) for item in self.available_stickers],
            "available_actions": [dict(item) for item in self.available_actions],
            "allowed_state_requests": list(self.allowed_state_requests),
            "forbidden_requests": list(self.forbidden_requests),
            "recent_ai_usage": dict(self.recent_ai_usage),
            "user_message": dict(self.user_message),
            "response_schema": dict(self.response_schema),
        }


@dataclass(slots=True, frozen=True)
class AIReplyV1:
    text: str = ""
    sticker_id: str | None = None
    action_id: str | None = None
    intent: AIIntent = AIIntent.CHAT
    state_request: Mapping[str, Any] | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "text": self.text,
            "sticker_id": self.sticker_id,
            "action_id": self.action_id,
            "intent": self.intent.value,
            "state_request": dict(self.state_request) if self.state_request else None,
        }


@dataclass(slots=True, frozen=True)
class EffectRequest:
    kind: EffectKind
    action_id: str | None = None
    item_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "action_id": self.action_id,
            "item_id": self.item_id,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True, frozen=True)
class ParseResult:
    reply: AIReplyV1
    effects: tuple[EffectRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    raw_text: str = ""


@dataclass(slots=True, frozen=True)
class ProviderResult:
    ok: bool
    content: str
    provider: str
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ChatTurnResult:
    user_message: ChatMessage
    pet_message: ChatMessage
    effects: tuple[EffectRequest, ...]
    warnings: tuple[str, ...]
    provider_result: ProviderResult
    request_payload: AIRequestPayload
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _enum_value(value: Any, enum_type: type[Enum], default: Any) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return default


def _message_type_value(value: Any) -> ChatMessageType:
    legacy = {"error": "system_notice", "system": "system_notice"}
    text = str(value or "").strip()
    return _enum_value(
        legacy.get(text, text),
        ChatMessageType,
        ChatMessageType.TEXT,
    )


def _normalize_legacy_sticker_message(
    message_type: ChatMessageType,
    sticker_id: str | None,
    text: str,
    metadata: dict[str, Any],
) -> tuple[ChatMessageType, str | None, str, dict[str, Any]]:
    if message_type != ChatMessageType.TEXT or sticker_id:
        return message_type, sticker_id, text, metadata
    match = LEGACY_STICKER_TEXT_RE.match(text.strip())
    if match is None:
        return message_type, sticker_id, text, metadata
    legacy_sticker_id = match.group("id").strip()
    if not legacy_sticker_id:
        return message_type, sticker_id, text, metadata
    label = match.group("label").strip()
    clean = dict(metadata)
    clean.setdefault("label", label or legacy_sticker_id)
    clean.setdefault("legacy_text_format", True)
    return ChatMessageType.STICKER, legacy_sticker_id, label, clean


def _optional_enum(value: Any, enum_type: type[Enum]) -> Any | None:
    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value)


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "AIIntent",
    "AIReplyV1",
    "AIRequestPayload",
    "AttachmentType",
    "ChatAttachment",
    "ChatMessage",
    "ChatMessageStatus",
    "ChatMessageType",
    "ChatSender",
    "ChatTurnResult",
    "EffectKind",
    "EffectRequest",
    "ParseResult",
    "PetContextSnapshot",
    "ProviderResult",
    "SCHEMA_VERSION",
    "VISUAL_STATES",
]

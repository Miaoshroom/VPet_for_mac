"""单轮离线聊天编排"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping

from core.chat.config import ChatConfig, load_chat_config
from core.chat.context_builder import ContextBuilder
from core.chat.history_store import HistoryStore
from core.chat.memory_commands import (
    ExplicitMemoryCommand,
    SENSITIVE_MEMORY_WARNING,
    parse_explicit_memory_command,
    parse_explicit_memory_delete_command,
)
from core.chat.memory_store import MemoryStore
from core.chat.models import (
    AIIntent,
    AIRequestPayload,
    ChatAttachment,
    ChatMessage,
    ChatMessageStatus,
    ChatMessageType,
    ChatSender,
    ChatTurnResult,
    ParseResult,
    ProviderResult,
)
from core.chat.ports import (
    ChatPetContextProvider,
    ChatProvider,
    Clock,
    IdGenerator,
    SystemClock,
    UUIDGenerator,
)
from core.chat.providers.deepseek import DeepSeekChatProvider
from core.chat.providers.fake import FakeChatProvider
from core.chat.reply_parser import ReplyParser

SENSITIVE_MEMORY_LOCAL_REPLY = "这个我不能帮你记，也不会发出去。"
SENSITIVE_MEMORY_REDACTED_TEXT = "[敏感显式记忆命令已隐藏]"


class ChatService:
    """统一负责一轮聊天的持久化

    后续界面可以乐观展示返回的用户消息标识
    但不应再次写入同一条消息
    """

    def __init__(
        self,
        *,
        config: ChatConfig | None = None,
        history_store: HistoryStore | None = None,
        memory_store: MemoryStore | None = None,
        context_builder: ContextBuilder | None = None,
        pet_context_provider: ChatPetContextProvider | None = None,
        provider: ChatProvider | None = None,
        parser: ReplyParser | None = None,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self.config = config or load_chat_config()
        self.history_store = history_store or HistoryStore(self.config.storage)
        self.memory_store = memory_store or MemoryStore(self.config.storage)
        self.context_builder = context_builder or ContextBuilder(
            config=self.config,
            history_store=self.history_store,
            memory_store=self.memory_store,
            pet_context_provider=pet_context_provider,
        )
        self.provider = provider or _provider_from_config(self.config)
        self.parser = parser or ReplyParser(self.config)
        self.clock = clock or SystemClock()
        self.id_generator = id_generator or UUIDGenerator()

    def send_user_message(
        self,
        text: str,
        *,
        attachments: Iterable[ChatAttachment] = (),
        metadata: Mapping[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> ChatTurnResult:
        user_message = ChatMessage(
            id=client_message_id or self.id_generator.new_id("user"),
            timestamp=self.clock.now().isoformat(),
            sender=ChatSender.USER,
            type=ChatMessageType.TEXT,
            text=str(text).strip(),
            attachments=tuple(attachments),
            status=ChatMessageStatus.SENT,
            metadata=dict(metadata or {}),
        )
        return self._complete_user_turn(user_message)

    def send_user_sticker(
        self,
        sticker_id: str,
        *,
        label: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> ChatTurnResult:
        sticker_id = str(sticker_id).strip()
        sticker = self.config.stickers.get(sticker_id)
        sticker_label = str(label or (sticker.label if sticker else sticker_id)).strip()
        if not sticker_label:
            sticker_label = sticker_id
        sticker_metadata = dict(metadata or {})
        sticker_metadata.setdefault("label", sticker_label)
        tags = _sticker_tags(sticker.metadata if sticker is not None else {})
        if tags and "tags" not in sticker_metadata:
            sticker_metadata["tags"] = list(tags)
        source = _optional_text(
            sticker_metadata.get("source")
            or (sticker.metadata.get("source") if sticker is not None else None)
        )
        if source is not None:
            sticker_metadata["source"] = source
        user_message = ChatMessage(
            id=client_message_id or self.id_generator.new_id("user"),
            timestamp=self.clock.now().isoformat(),
            sender=ChatSender.USER,
            type=ChatMessageType.STICKER,
            text=sticker_label,
            sticker_id=sticker_id,
            status=ChatMessageStatus.SENT,
            metadata=sticker_metadata,
        )
        return self._complete_user_turn(user_message)

    def _complete_user_turn(self, user_message: ChatMessage) -> ChatTurnResult:
        memory_command = parse_explicit_memory_command(user_message.text)
        if (
            memory_command is not None
            and memory_command.warning == SENSITIVE_MEMORY_WARNING
        ):
            return self._sensitive_memory_rejected_turn(user_message, memory_command)

        self.history_store.append(user_message)
        delete_turn = self._memory_delete_proposal_turn(user_message)
        if delete_turn is not None:
            return delete_turn

        user_message, turn_metadata, memory_warnings = self._handle_explicit_memory(
            user_message,
            memory_command,
        )

        payload = self.context_builder.build(user_message=user_message)
        provider_result = self.provider.complete(payload)
        if not provider_result.ok:
            return self._provider_failure(
                user_message,
                payload,
                provider_result,
                turn_metadata,
                memory_warnings,
            )

        parse_result = self.parser.parse(provider_result.content)
        parse_result = _apply_recent_sticker_limit(parse_result, payload)
        warnings = _dedupe_warnings([*memory_warnings, *parse_result.warnings])
        pet_message = ChatMessage(
            id=self.id_generator.new_id("lolith"),
            timestamp=self.clock.now().isoformat(),
            sender=ChatSender.LOLITH,
            type=_reply_message_type(
                parse_result.reply.text,
                parse_result.reply.sticker_id,
            ),
            text=parse_result.reply.text,
            sticker_id=parse_result.reply.sticker_id,
            status=ChatMessageStatus.SENT,
            action_id=parse_result.reply.action_id,
            intent=parse_result.reply.intent,
            state_request=parse_result.reply.state_request,
            pet_state_snapshot={
                "pet_state": dict(payload.pet_state),
                "visual_state": payload.visual_state,
            },
            parse_warnings=warnings,
            provider=provider_result.provider,
        )
        self.history_store.append(pet_message)
        return ChatTurnResult(
            user_message=user_message,
            pet_message=pet_message,
            effects=parse_result.effects,
            warnings=warnings,
            provider_result=provider_result,
            request_payload=payload,
            metadata=turn_metadata,
        )

    def _handle_explicit_memory(
        self,
        user_message: ChatMessage,
        command: ExplicitMemoryCommand | None,
    ) -> tuple[ChatMessage, dict[str, Any], tuple[str, ...]]:
        if command is None:
            return user_message, {}, ()

        warnings: list[str] = []
        memory_status: dict[str, Any] = {
            "status": command.status,
            "source": "user_explicit",
        }
        if command.warning == "explicit_memory_sensitive_rejected":
            warnings.append(command.warning)
        if not command.can_write:
            return _with_explicit_memory_metadata(user_message, memory_status), {
                "explicit_memory": memory_status
            }, tuple(warnings)

        try:
            write_result = self.memory_store.append_manual_note(
                command.note_text,
                source_message_id=user_message.id,
                source="user_explicit",
                actor="user",
            )
        except (OSError, ValueError) as exc:
            warning = f"explicit_memory_write_failed:{type(exc).__name__}"
            warnings.append(warning)
            memory_status = {
                "status": "error",
                "source": "user_explicit",
                "warning": warning,
            }
            return _with_explicit_memory_metadata(user_message, memory_status), {
                "explicit_memory": memory_status
            }, tuple(warnings)

        memory_status = {
            "status": write_result.status,
            "source": "user_explicit",
            "text": write_result.text,
        }
        if write_result.status == "saved":
            memory_status["backup_created"] = write_result.backup_path is not None
        return _with_explicit_memory_metadata(user_message, memory_status), {
            "explicit_memory": memory_status
        }, tuple(warnings)

    def _sensitive_memory_rejected_turn(
        self,
        user_message: ChatMessage,
        command: ExplicitMemoryCommand,
    ) -> ChatTurnResult:
        warning = command.warning or SENSITIVE_MEMORY_WARNING
        warnings = (warning,)
        memory_status: dict[str, Any] = {
            "status": command.status,
            "source": "user_explicit",
            "warning": warning,
        }
        redacted_user_message = _with_explicit_memory_metadata(
            replace(user_message, text=SENSITIVE_MEMORY_REDACTED_TEXT),
            memory_status,
        )
        self.history_store.append(redacted_user_message)
        payload = self.context_builder.build(user_message=redacted_user_message)
        pet_message = ChatMessage(
            id=self.id_generator.new_id("lolith"),
            timestamp=self.clock.now().isoformat(),
            sender=ChatSender.LOLITH,
            type=ChatMessageType.TEXT,
            text=SENSITIVE_MEMORY_LOCAL_REPLY,
            status=ChatMessageStatus.SENT,
            intent=AIIntent.FALLBACK,
            pet_state_snapshot={
                "pet_state": dict(payload.pet_state),
                "visual_state": payload.visual_state,
            },
            parse_warnings=warnings,
            provider="local_memory",
        )
        self.history_store.append(pet_message)
        return ChatTurnResult(
            user_message=redacted_user_message,
            pet_message=pet_message,
            effects=(),
            warnings=warnings,
            provider_result=ProviderResult(
                ok=True,
                content="",
                provider="local_memory",
                metadata={"explicit_memory": memory_status},
            ),
            request_payload=payload,
            metadata={"explicit_memory": memory_status},
        )

    def _provider_failure(
        self,
        user_message: ChatMessage,
        payload: Any,
        provider_result: ProviderResult,
        turn_metadata: Mapping[str, Any] | None = None,
        memory_warnings: tuple[str, ...] = (),
    ) -> ChatTurnResult:
        warning = provider_result.error or "provider_failed"
        memory_status = _explicit_memory_status(turn_metadata or {})
        text = "我现在没法好好回应，先把这次失败记录下来。"
        if memory_status == "saved":
            text = "我先记下来了，但刚刚有点没连上。"
        pet_message = ChatMessage(
            id=self.id_generator.new_id("lolith"),
            timestamp=self.clock.now().isoformat(),
            sender=ChatSender.LOLITH,
            type=ChatMessageType.SYSTEM_NOTICE,
            text=text,
            status=ChatMessageStatus.FAILED,
            intent=AIIntent.FALLBACK,
            parse_warnings=_dedupe_warnings([*memory_warnings, warning]),
            provider=provider_result.provider,
        )
        self.history_store.append(pet_message)
        return ChatTurnResult(
            user_message=user_message,
            pet_message=pet_message,
            effects=(),
            warnings=_dedupe_warnings([*memory_warnings, warning]),
            provider_result=provider_result,
            request_payload=payload,
            metadata=dict(turn_metadata or {}),
        )

    def _memory_delete_proposal_turn(
        self,
        user_message: ChatMessage,
    ) -> ChatTurnResult | None:
        command = parse_explicit_memory_delete_command(user_message.text)
        if command is None:
            return None

        warnings = (command.warning,) if command.warning else ()
        proposal: dict[str, Any] = {
            "status": command.status,
            "source": "user_explicit",
        }
        text = "我还没看出要删哪条记忆。"
        if command.status == "rejected_clear_all":
            text = "清空全部记忆太危险啦，先去记忆面板里手动处理吧。"
        elif command.status == "rejected_protected_target":
            text = "这类资料不能在聊天里删，先去设置或记忆面板里手动处理吧。"
        elif command.can_propose:
            candidates = self.memory_store.find_manual_notes(command.query)
            proposal["query"] = command.query
            proposal["candidates"] = [
                candidate.to_preview_dict() for candidate in candidates
            ]
            if not candidates:
                proposal["status"] = "not_found"
                text = "没找到相关记忆。"
            elif len(candidates) == 1:
                proposal["status"] = "needs_confirmation"
                preview = str(candidates[0].to_preview_dict()["text"])
                text = f"我找到这条记忆，要删掉吗？\n“{preview}”"
            else:
                proposal["status"] = "multiple_candidates"
                text = "我找到几条相关记忆，先去记忆面板里确认要删哪条吧。"

        payload = self.context_builder.build(user_message=user_message)
        pet_message = ChatMessage(
            id=self.id_generator.new_id("lolith"),
            timestamp=self.clock.now().isoformat(),
            sender=ChatSender.LOLITH,
            type=ChatMessageType.TEXT,
            text=text,
            status=ChatMessageStatus.SENT,
            intent=AIIntent.CHAT,
            pet_state_snapshot={
                "pet_state": dict(payload.pet_state),
                "visual_state": payload.visual_state,
            },
            parse_warnings=warnings,
            provider="local_memory",
        )
        self.history_store.append(pet_message)
        return ChatTurnResult(
            user_message=user_message,
            pet_message=pet_message,
            effects=(),
            warnings=warnings,
            provider_result=ProviderResult(
                ok=True,
                content="",
                provider="local_memory",
                metadata={"memory_delete_proposal": proposal},
            ),
            request_payload=payload,
            metadata={"memory_delete_proposal": proposal},
        )


def _provider_from_config(config: ChatConfig) -> ChatProvider:
    provider = str(config.ai_settings.get("provider", "fake")).strip().lower()
    if provider == "deepseek":
        return DeepSeekChatProvider(config)
    return FakeChatProvider()


def _sticker_tags(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    raw_tags = metadata.get("tags", ())
    if not isinstance(raw_tags, list | tuple):
        return ()
    return tuple(str(tag).strip() for tag in raw_tags if str(tag).strip())


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _apply_recent_sticker_limit(
    parse_result: ParseResult,
    payload: AIRequestPayload,
) -> ParseResult:
    if parse_result.reply.sticker_id is None:
        return parse_result
    if not _recent_ai_usage_blocks_sticker(payload):
        return parse_result
    warnings = list(parse_result.warnings)
    warnings.append("recent_ai_usage:sticker_rate_limited")
    text = parse_result.reply.text
    if not text:
        text = "我先用文字陪你一下。"
        warnings.append("empty_text_after_sticker_rate_limit_fallback")
    return replace(
        parse_result,
        reply=replace(parse_result.reply, text=text, sticker_id=None),
        warnings=_dedupe_warnings(warnings),
    )


def _recent_ai_usage_blocks_sticker(payload: AIRequestPayload) -> bool:
    usage = dict(payload.recent_ai_usage)
    bool_keys = (
        "sticker_used_in_recent_lolith_turns",
        "sticker_used_recently",
        "recent_sticker_used",
    )
    if any(_truthy(usage.get(key)) for key in bool_keys):
        return True
    for key in (
        "last_sticker_turns_ago",
        "turns_since_sticker",
        "sticker_turns_ago",
    ):
        value = _int_or_none(usage.get(key))
        if value is not None and 0 <= value <= 2:
            return True
    count = _int_or_none(usage.get("recent_lolith_sticker_count_2"))
    if count is not None and count > 0:
        return True
    return _recent_messages_have_lolith_sticker(payload.recent_messages)


def _recent_messages_have_lolith_sticker(
    recent_messages: tuple[Mapping[str, Any], ...],
) -> bool:
    seen_lolith_turns = 0
    for message in reversed(recent_messages):
        if str(message.get("sender", "")).strip() != ChatSender.LOLITH.value:
            continue
        seen_lolith_turns += 1
        if str(message.get("sticker_id") or "").strip():
            return True
        if seen_lolith_turns >= 2:
            break
    return False


def _reply_message_type(text: str, sticker_id: str | None) -> ChatMessageType:
    if sticker_id is None:
        return ChatMessageType.TEXT
    if text:
        return ChatMessageType.MIXED
    return ChatMessageType.STICKER


def _with_explicit_memory_metadata(
    user_message: ChatMessage,
    memory_status: Mapping[str, Any],
) -> ChatMessage:
    metadata = dict(user_message.metadata)
    metadata["explicit_memory"] = dict(memory_status)
    return replace(user_message, metadata=metadata)


def _explicit_memory_status(metadata: Mapping[str, Any]) -> str:
    explicit_memory = metadata.get("explicit_memory")
    if not isinstance(explicit_memory, Mapping):
        return ""
    return str(explicit_memory.get("status") or "")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe_warnings(warnings: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    clean: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        clean.append(warning)
    return tuple(clean)


__all__ = ["ChatService"]

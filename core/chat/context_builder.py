"""从聊天存储和宠物快照构建提供方请求包"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from core.chat.config import ChatConfig, DEFAULT_USER_PROFILE, load_chat_config
from core.chat.history_store import HistoryStore
from core.chat.memory_store import MemoryStore
from core.chat.models import AIRequestPayload, ChatMessage, PetContextSnapshot, VISUAL_STATES
from core.chat.ports import ChatPetContextProvider


class StaticChatPetContextProvider:
    """用于第一阶段离线测试的简易假上下文提供方"""

    def __init__(self, snapshot: PetContextSnapshot | None = None) -> None:
        self._snapshot = snapshot or PetContextSnapshot(
            pet_state={
                "satiety": 80,
                "mood": 80,
                "energy": 80,
                "health": 100,
                "cleanliness": 80,
            },
            runtime_state={"mode": "offline_chat"},
            visual_state="normal",
            inventory=(),
            active_activity="待机",
        )

    def snapshot(self) -> PetContextSnapshot:
        return self._snapshot


class ContextBuilder:
    def __init__(
        self,
        *,
        config: ChatConfig | None = None,
        history_store: HistoryStore | None = None,
        memory_store: MemoryStore | None = None,
        pet_context_provider: ChatPetContextProvider | None = None,
    ) -> None:
        self.config = config or load_chat_config()
        self.history_store = history_store or HistoryStore(self.config.storage)
        self.memory_store = memory_store or MemoryStore(self.config.storage)
        self.pet_context_provider = (
            pet_context_provider or StaticChatPetContextProvider()
        )

    def build(
        self,
        *,
        user_message: ChatMessage,
        recent_messages: Sequence[ChatMessage] | None = None,
    ) -> AIRequestPayload:
        snapshot = self.pet_context_provider.snapshot()
        visual_state = _normalize_visual_state(snapshot.visual_state)
        runtime_state = _sanitize_runtime_state(snapshot.runtime_state)
        if recent_messages is None:
            recent_messages = self.history_store.load_recent(
                days=self.config.storage.recent_history_days,
                limit=self.config.storage.recent_history_limit,
            )
        recent_messages = _exclude_current_message(recent_messages, user_message.id)
        recent_ai_usage = _recent_ai_usage(snapshot.recent_ai_usage, recent_messages)
        return AIRequestPayload(
            conversation_goal=self.config.conversation_goal,
            persona=self.config.persona,
            user_profile=_prompt_user_profile(self.config.user_profile),
            style_rules=self.config.style_rules,
            time_context=_time_context(),
            pet_state=dict(snapshot.pet_state),
            runtime_state=runtime_state,
            visual_state=visual_state,
            inventory=tuple(dict(item) for item in snapshot.inventory),
            active_activity=snapshot.active_activity,
            recent_messages=tuple(
                message.to_context_dict() for message in recent_messages
            ),
            long_term_memory=self.memory_store.load(),
            available_stickers=self.config.available_stickers(),
            available_actions=self.config.available_actions(allowed_only=True),
            allowed_state_requests=self.config.allowed_state_requests,
            forbidden_requests=self.config.forbidden_requests,
            recent_ai_usage=recent_ai_usage,
            user_message=user_message.to_context_dict(),
            response_schema=self.config.response_schema,
        )


def _normalize_visual_state(value: object) -> str:
    text = str(value or "").strip()
    if text in VISUAL_STATES:
        return text
    return "normal"


def _exclude_current_message(
    messages: Sequence[ChatMessage],
    current_message_id: str,
) -> tuple[ChatMessage, ...]:
    return tuple(message for message in messages if message.id != current_message_id)


def _recent_ai_usage(
    snapshot_usage: Mapping[str, Any],
    recent_messages: Sequence[ChatMessage],
) -> dict[str, Any]:
    usage = dict(snapshot_usage)
    recent_lolith_turns = [
        message
        for message in reversed(recent_messages)
        if message.sender.value == "lolith"
    ][:2]
    turns_since_sticker: int | None = None
    for index, message in enumerate(recent_lolith_turns, start=1):
        if message.sticker_id:
            turns_since_sticker = index
            break
    usage.setdefault(
        "sticker_used_in_recent_lolith_turns",
        turns_since_sticker is not None,
    )
    usage.setdefault("last_sticker_turns_ago", turns_since_sticker)
    usage.setdefault(
        "recent_lolith_sticker_count_2",
        sum(1 for message in recent_lolith_turns if message.sticker_id),
    )
    return usage


def _time_context() -> dict[str, str]:
    now = datetime.now().astimezone()
    return {
        "now": now.isoformat(),
        "date": now.date().isoformat(),
        "time": now.time().replace(microsecond=0).isoformat(),
        "timezone": now.tzname() or "",
    }


def _sanitize_runtime_state(value: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key == "visual_state":
            clean[key] = _normalize_visual_state(item)
        elif isinstance(item, Mapping):
            clean[key] = _sanitize_runtime_state(item)
        else:
            clean[key] = item
    return clean


def _prompt_user_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    """Build the small, prompt-safe user profile visible to the model."""

    profile = dict(DEFAULT_USER_PROFILE)
    profile.update(dict(value))
    editing = _dict_value(profile.get("profile_editing"))
    return {
        "schema_version": profile.get("schema_version", 1),
        "profile_id": _clip_text(profile.get("profile_id"), 64),
        "display_name": _clip_text(profile.get("display_name"), 48),
        "preferred_name": _clip_text(profile.get("preferred_name"), 48),
        "preferred_pronouns": _clip_text(profile.get("preferred_pronouns"), 32),
        "pet_call_user": (
            _clip_text(profile.get("pet_call_user"), 24)
            or str(DEFAULT_USER_PROFILE["pet_call_user"])
        ),
        "avatar": _avatar_summary(profile.get("avatar")),
        "relationship_to_pet": _clip_text(profile.get("relationship_to_pet"), 48)
        or str(DEFAULT_USER_PROFILE["relationship_to_pet"]),
        "chat_preferences": _prompt_chat_preferences(profile.get("chat_preferences")),
        "boundaries": _prompt_boundaries(profile.get("boundaries")),
        "profile_editing": {
            "ai_may_modify": False,
            "source_of_truth": _clip_text(
                editing.get("source_of_truth", "human_edit_only"),
                48,
            )
            or "human_edit_only",
            "instruction": _clip_text(
                editing.get(
                    "instruction",
                    "用户资料只能由用户或程序设置页人工修改，AI 不能声称自己已经修改 user_profile。",
                ),
                120,
            ),
        },
        "notes": _string_list(profile.get("notes"), max_items=6, max_len=120),
    }


def _prompt_chat_preferences(value: Any) -> dict[str, str]:
    defaults = _dict_value(DEFAULT_USER_PROFILE["chat_preferences"])
    data = _dict_value(value)
    return {
        key: _clip_text(data.get(key, defaults.get(key, "")), 80)
        for key in (
            "reply_length",
            "comfort_style",
            "teasing_level",
            "advice_style",
            "emoji_or_sticker_preference",
        )
    }


def _prompt_boundaries(value: Any) -> dict[str, list[str]]:
    defaults = _dict_value(DEFAULT_USER_PROFILE["boundaries"])
    data = _dict_value(value)
    return {
        "avoid_topics": _string_list(
            data.get("avoid_topics", defaults.get("avoid_topics")),
            max_items=12,
            max_len=80,
        ),
        "avoid_tone": _string_list(
            data.get("avoid_tone", defaults.get("avoid_tone")),
            max_items=12,
            max_len=80,
        ),
        "never_call_user": _string_list(
            data.get("never_call_user", defaults.get("never_call_user")),
            max_items=12,
            max_len=80,
        ),
    }


def _avatar_summary(value: Any) -> dict[str, Any]:
    if not value:
        return {"configured": False}
    if not isinstance(value, Mapping):
        return {"configured": True}
    return {
        "configured": True,
        "kind": _clip_text(value.get("kind"), 32),
        "label": _clip_text(value.get("label"), 48),
    }


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _string_list(value: Any, *, max_items: int, max_len: int) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list | tuple):
        raw_items = list(value)
    else:
        raw_items = []
    return [
        text
        for text in (_clip_text(item, max_len) for item in raw_items[:max_items])
        if text
    ]


def _clip_text(value: Any, max_len: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


__all__ = ["ContextBuilder", "StaticChatPetContextProvider"]

"""离线聊天核心的配置读取"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.app_paths import resource_root

CHAT_CONFIG_DIR = "chat"
API_KEY_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PET_PERSONA_FILENAME = "pet_persona.json"
PET_STICKERS_FILENAME = "pet_stickers.json"
LEGACY_CHAT_CONFIG_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("lolith_persona.json", PET_PERSONA_FILENAME),
    ("lolith_stickers.json", PET_STICKERS_FILENAME),
)

DEFAULT_AI_SETTINGS: dict[str, Any] = {
    "schema_version": 1,
    "provider": "fake",
    "model": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "api_key_file": "config/chat/api_key.local.json",
    "timeout_seconds": 30,
    "retries": 1,
    "temperature": 0.7,
    "max_tokens": 800,
}

DEFAULT_STORAGE: dict[str, Any] = {
    "schema_version": 1,
    "history_dir": "chat_data/history",
    "memory_dir": "chat_data/memory",
    "pet_stickers_dir": "chat_data/pet_stickers",
    "user_stickers_dir": "chat_data/user_stickers",
    "attachments_dir": "chat_data/attachments",
    "long_term_memory_file": "chat_data/memory/long_term_memory.json",
    "recent_history_days": 7,
    "recent_history_limit": 40,
}

DEFAULT_PERSONA: dict[str, Any] = {
    "schema_version": 1,
    "name": "萝莉斯",
    "summary": "一位温柔、活泼、会照顾边界的 macOS 桌宠伙伴。",
    "tone": ["简短", "亲近", "不越权"],
}

DEFAULT_USER_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "profile_id": "local_user",
    "display_name": "",
    "preferred_name": "",
    "preferred_pronouns": "",
    "pet_call_user": "主人",
    "avatar": {
        "kind": "unset",
        "label": "",
    },
    "relationship_to_pet": "桌宠的主人",
    "chat_preferences": {
        "reply_length": "短句优先，复杂问题再稍微展开",
        "comfort_style": "先陪伴和接住情绪，再给很小的下一步",
        "teasing_level": "轻微吐槽和撒娇可以，不能油腻或冒犯",
        "advice_style": "少说教，只给清楚、可执行的小建议",
        "emoji_or_sticker_preference": "emoji 和贴纸都克制使用",
    },
    "boundaries": {
        "avoid_topics": [],
        "avoid_tone": ["客服腔", "心理咨询模板", "长篇说教"],
        "never_call_user": [],
    },
    "profile_editing": {
        "ai_may_modify": False,
        "source_of_truth": "human_edit_only",
        "instruction": "用户资料只能由用户或程序设置页人工修改，AI 不能声称自己已经修改 user_profile。",
    },
    "notes": [
        "人工写入的短备注放在这里；不要填写真实隐私、密钥、内部路径或长期记忆。",
    ],
}

DEFAULT_FORBIDDEN_REQUESTS: tuple[str, ...] = (
    "delete_chat_history",
    "delete_memory",
    "memory_update",
    "modify_memory",
    "modify_persona",
    "modify_user_profile",
    "modify_api_settings",
    "modify_pet_state",
    "modify_save_game",
    "modify_money",
    "modify_inventory",
    "modify_activity_progress",
    "set_visual_state",
    "use_any_state",
)

DEFAULT_PROMPT_RULES: dict[str, Any] = {
    "schema_version": 1,
    "conversation_goal": "陪伴用户完成自然、安全、边界清晰的桌宠对话",
    "style_rules": [
        "回复默认 1-2 句，像朋友聊天，简短自然，不客服，不作文。",
        "用户提出复杂问题时可以稍微长一点，但仍保持清楚克制。",
        "sticker_id 默认 null，action_id 每次回复都必须从 available_actions 中按语气匹配四选一：say_self(自言自语)、say_serious(严肃说话)、say_shining(发光说话)、say_shy(害羞说话)。",
        "state_request 默认 null，不要为了普通聊天主动填。",
        "可以提出动作或物品使用请求，但不能直接修改养成状态。",
        "PetState 是真实养成状态，只读；visual_state 是表现状态，any 不是状态。",
        "只返回 response_schema 指定的 JSON 对象，必须包含所有字段。",
    ],
    "allowed_state_requests": ["use_item"],
    "forbidden_requests": list(DEFAULT_FORBIDDEN_REQUESTS),
    "response_schema": {
        "schema_version": 1,
        "text": "string",
        "sticker_id": "string|null",
        "action_id": "string|null",
        "intent": "chat|action_request|use_item_request|fallback",
        "state_request": "null|{'type':'use_item','item_id':'string'}",
    },
}

DEFAULT_STICKERS: dict[str, Any] = {
    "schema_version": 1,
    "stickers": [
        {"id": "sticker_01", "label": "开心"},
        {"id": "sticker_02", "label": "思考"},
        {"id": "sticker_03", "label": "担心"},
    ],
}

DEFAULT_AI_ACTIONS: dict[str, Any] = {
    "schema_version": 1,
    "actions": [
        {"id": "say_self", "label": "自言自语", "allow_in_v1": True},
        {"id": "say_serious", "label": "严肃说话", "allow_in_v1": True},
        {"id": "say_shining", "label": "发光说话", "allow_in_v1": True},
        {"id": "say_shy", "label": "害羞说话", "allow_in_v1": True},
    ],
    "allowed_use_item_ids": [
        "rice_ball",
        "sparkling_water",
        "basic_medicine",
        "cleaning_wipes",
        "gift_box",
    ],
}


@dataclass(slots=True, frozen=True)
class ChatStoragePaths:
    history_dir: Path
    memory_dir: Path
    pet_stickers_dir: Path
    user_stickers_dir: Path
    attachments_dir: Path
    long_term_memory_file: Path
    recent_history_days: int = 7
    recent_history_limit: int = 40


@dataclass(slots=True, frozen=True)
class ChatStickerSpec:
    id: str
    label: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "label": self.label}
        tags = _string_list(self.metadata.get("tags"))
        if tags:
            payload["tags"] = list(tags)
        scenarios = _string_list(self.metadata.get("scenarios"))
        if scenarios:
            payload["scenarios"] = list(scenarios)
        return payload


@dataclass(slots=True, frozen=True)
class ChatActionSpec:
    id: str
    label: str
    allow_in_v1: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "allow_in_v1": self.allow_in_v1,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True, frozen=True)
class ChatConfig:
    config_dir: Path
    project_root: Path
    ai_settings: Mapping[str, Any]
    storage: ChatStoragePaths
    persona: Mapping[str, Any]
    user_profile: Mapping[str, Any]
    conversation_goal: str
    style_rules: tuple[str, ...]
    response_schema: Mapping[str, Any]
    allowed_state_requests: tuple[str, ...]
    forbidden_requests: tuple[str, ...]
    stickers: Mapping[str, ChatStickerSpec]
    actions: Mapping[str, ChatActionSpec]
    allowed_use_item_ids: frozenset[str]

    def available_stickers(self) -> tuple[dict[str, Any], ...]:
        return tuple(sticker.to_dict() for sticker in self.stickers.values())

    def available_actions(self, *, allowed_only: bool = True) -> tuple[dict[str, Any], ...]:
        actions = self.actions.values()
        if allowed_only:
            actions = [action for action in actions if action.allow_in_v1]
        return tuple(action.to_dict() for action in actions)


def load_chat_config(
    *,
    config_dir: Path | None = None,
    project_root: Path | None = None,
) -> ChatConfig:
    """读取聊天配置 缺失文件时回退默认值

    当前项目把内置配置放在 ``config/`` 下
    为了贴合现有风格 读取时不自动创建缺失配置文件
    """

    root = project_root or resource_root()
    chat_config_dir = config_dir or root / "config" / CHAT_CONFIG_DIR
    _migrate_legacy_chat_config_files(chat_config_dir)

    ai_settings = _load_dict(
        chat_config_dir / "ai_settings.json", DEFAULT_AI_SETTINGS
    )
    storage = _load_dict(chat_config_dir / "storage.json", DEFAULT_STORAGE)
    persona = _load_dict(chat_config_dir / PET_PERSONA_FILENAME, DEFAULT_PERSONA)
    user_profile = _load_dict(
        chat_config_dir / "user_profile.json", DEFAULT_USER_PROFILE
    )
    prompt_rules = _load_dict(
        chat_config_dir / "prompt_rules.json", DEFAULT_PROMPT_RULES
    )
    sticker_payload = _load_dict(
        chat_config_dir / PET_STICKERS_FILENAME, DEFAULT_STICKERS
    )
    action_payload = _load_dict(chat_config_dir / "ai_actions.json", DEFAULT_AI_ACTIONS)

    clean_ai_settings = _clean_ai_settings(ai_settings)
    paths = _storage_paths(storage, root)
    stickers = _sticker_specs(sticker_payload)
    actions = _action_specs(action_payload)
    style_rules = _string_tuple(prompt_rules.get("style_rules"))
    if not style_rules:
        style_rules = _string_tuple(DEFAULT_PROMPT_RULES["style_rules"])
    conversation_goal = str(
        prompt_rules.get("conversation_goal", DEFAULT_PROMPT_RULES["conversation_goal"])
    ).strip()
    if not conversation_goal:
        conversation_goal = str(DEFAULT_PROMPT_RULES["conversation_goal"])
    allowed_state_requests = _string_tuple(prompt_rules.get("allowed_state_requests"))
    if not allowed_state_requests:
        allowed_state_requests = _string_tuple(
            DEFAULT_PROMPT_RULES["allowed_state_requests"]
        )
    forbidden = _string_tuple(prompt_rules.get("forbidden_requests"))
    if not forbidden:
        forbidden = DEFAULT_FORBIDDEN_REQUESTS
    response_schema = _dict_value(prompt_rules.get("response_schema"))
    if not response_schema:
        response_schema = dict(DEFAULT_PROMPT_RULES["response_schema"])
    allowed_use_items = frozenset(_string_tuple(action_payload.get("allowed_use_item_ids")))

    return ChatConfig(
        config_dir=chat_config_dir,
        project_root=root,
        ai_settings=clean_ai_settings,
        storage=paths,
        persona=_dict_value(persona) or dict(DEFAULT_PERSONA),
        user_profile=_user_profile_value(user_profile),
        conversation_goal=conversation_goal,
        style_rules=style_rules,
        response_schema=response_schema,
        allowed_state_requests=allowed_state_requests,
        forbidden_requests=forbidden,
        stickers=stickers,
        actions=actions,
        allowed_use_item_ids=allowed_use_items,
    )


def _migrate_legacy_chat_config_files(chat_config_dir: Path) -> None:
    for legacy_name, current_name in LEGACY_CHAT_CONFIG_MIGRATIONS:
        legacy_path = chat_config_dir / legacy_name
        current_path = chat_config_dir / current_name
        if current_path.exists() or not legacy_path.exists():
            continue
        try:
            legacy_path.rename(current_path)
        except OSError:
            pass


def _load_dict(path: Path, default: Mapping[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(default)
    if not isinstance(payload, dict):
        return dict(default)
    merged = dict(default)
    merged.update(payload)
    return merged


def _clean_ai_settings(data: Mapping[str, Any]) -> dict[str, Any]:
    clean = dict(DEFAULT_AI_SETTINGS)
    provider = str(data.get("provider", clean["provider"])).strip()
    model = str(data.get("model", clean["model"])).strip()
    clean["provider"] = provider or clean["provider"]
    clean["model"] = model or clean["model"]
    clean["timeout_seconds"] = max(1, _int_value(data.get("timeout_seconds"), 30))
    clean["retries"] = max(0, _int_value(data.get("retries"), 1))
    clean["temperature"] = min(
        2.0,
        max(0.0, _float_value(data.get("temperature"), 0.7)),
    )
    clean["max_tokens"] = max(1, _int_value(data.get("max_tokens"), 800))
    api_key_env = str(data.get("api_key_env", clean["api_key_env"])).strip()
    if API_KEY_ENV_RE.match(api_key_env):
        clean["api_key_env"] = api_key_env
    api_key_file = str(data.get("api_key_file", clean["api_key_file"])).strip()
    clean["api_key_file"] = api_key_file or clean["api_key_file"]
    return clean


def _storage_paths(data: Mapping[str, Any], root: Path) -> ChatStoragePaths:
    return ChatStoragePaths(
        history_dir=_resolve_path(data.get("history_dir"), root, "chat_data/history"),
        memory_dir=_resolve_path(data.get("memory_dir"), root, "chat_data/memory"),
        pet_stickers_dir=_resolve_path(
            data.get("pet_stickers_dir", data.get("pet_sticker_dir")),
            root,
            "chat_data/pet_stickers",
        ),
        user_stickers_dir=_resolve_path(
            data.get("user_stickers_dir", data.get("user_sticker_dir")),
            root,
            "chat_data/user_stickers",
        ),
        attachments_dir=_resolve_path(
            data.get("attachments_dir"), root, "chat_data/attachments"
        ),
        long_term_memory_file=_resolve_path(
            data.get("long_term_memory_file"),
            root,
            "chat_data/memory/long_term_memory.json",
        ),
        recent_history_days=max(1, _int_value(data.get("recent_history_days"), 7)),
        recent_history_limit=max(1, _int_value(data.get("recent_history_limit"), 40)),
    )


def _resolve_path(value: Any, root: Path, default: str) -> Path:
    text = str(value or default).strip() or default
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return root / path


def _sticker_specs(data: Mapping[str, Any]) -> dict[str, ChatStickerSpec]:
    specs: dict[str, ChatStickerSpec] = {}
    raw_items = data.get("stickers")
    if not isinstance(raw_items, list):
        raw_items = DEFAULT_STICKERS["stickers"]
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        sticker_id = str(item.get("id", "")).strip()
        if not sticker_id:
            continue
        specs[sticker_id] = ChatStickerSpec(
            id=sticker_id,
            label=str(item.get("label", sticker_id)).strip() or sticker_id,
            metadata=_dict_value(item.get("metadata")),
        )
    if specs:
        return specs
    return _sticker_specs(DEFAULT_STICKERS)


def _action_specs(data: Mapping[str, Any]) -> dict[str, ChatActionSpec]:
    specs: dict[str, ChatActionSpec] = {}
    raw_items = data.get("actions")
    if not isinstance(raw_items, list):
        raw_items = DEFAULT_AI_ACTIONS["actions"]
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        action_id = str(item.get("id", "")).strip()
        if not action_id:
            continue
        specs[action_id] = ChatActionSpec(
            id=action_id,
            label=str(item.get("label", action_id)).strip() or action_id,
            allow_in_v1=bool(item.get("allow_in_v1", False)),
            metadata=_dict_value(item.get("metadata")),
        )
    if specs:
        return specs
    return _action_specs(DEFAULT_AI_ACTIONS)


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _user_profile_value(value: Any) -> dict[str, Any]:
    data = _dict_value(value)
    clean = _deep_dict(DEFAULT_USER_PROFILE)
    for key, item in data.items():
        if key in {"chat_preferences", "boundaries", "profile_editing", "avatar"}:
            default_item = clean.get(key)
            if isinstance(default_item, Mapping) and isinstance(item, Mapping):
                nested = dict(default_item)
                nested.update(item)
                clean[key] = nested
            else:
                clean[key] = item
        else:
            clean[key] = item
    return clean


def _deep_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            clean[key] = _deep_dict(item)
        elif isinstance(item, list):
            clean[key] = list(item)
        else:
            clean[key] = item
    return clean


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "ChatActionSpec",
    "ChatConfig",
    "ChatStickerSpec",
    "ChatStoragePaths",
    "DEFAULT_AI_ACTIONS",
    "DEFAULT_AI_SETTINGS",
    "DEFAULT_PERSONA",
    "DEFAULT_PROMPT_RULES",
    "DEFAULT_STICKERS",
    "DEFAULT_STORAGE",
    "DEFAULT_USER_PROFILE",
    "load_chat_config",
]

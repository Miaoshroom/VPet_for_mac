"""DeepSeek 聊天提供方"""

from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from core.chat.config import ChatConfig
from core.chat.models import AIRequestPayload, ProviderResult

DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
HttpPost = Callable[[str, dict[str, str], bytes, float], tuple[int, str]]


class DeepSeekChatProvider:
    def __init__(
        self,
        config: ChatConfig,
        *,
        endpoint: str = DEEPSEEK_ENDPOINT,
        http_post: HttpPost | None = None,
    ) -> None:
        self.config = config
        self.endpoint = endpoint
        self.http_post = http_post or _urllib_post

    def complete(self, payload: AIRequestPayload) -> ProviderResult:
        api_key = _load_api_key(self.config)
        if not api_key:
            return ProviderResult(
                ok=False,
                content="",
                provider="deepseek",
                error="missing_api_key",
            )

        body = _request_body(payload, self.config)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        timeout = float(self.config.ai_settings.get("timeout_seconds", 30))
        retries = int(self.config.ai_settings.get("retries", 1))
        attempts = max(1, retries + 1)
        last_error = "deepseek_request_failed"
        for _ in range(attempts):
            try:
                status, response_text = self.http_post(
                    self.endpoint,
                    headers,
                    json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    timeout,
                )
            except (OSError, TimeoutError, ValueError):
                last_error = "deepseek_request_failed"
                continue
            if status < 200 or status >= 300:
                last_error = f"deepseek_http_{status}"
                continue
            content = _extract_content(response_text)
            if content is None:
                last_error = "deepseek_bad_response"
                continue
            return ProviderResult(
                ok=True,
                content=content,
                provider="deepseek",
                metadata={"model": body["model"]},
            )
        return ProviderResult(
            ok=False,
            content="",
            provider="deepseek",
            error=last_error,
        )


def _load_api_key(config: ChatConfig) -> str:
    api_key_env = str(config.ai_settings.get("api_key_env", "")).strip()
    api_key = os.environ.get(api_key_env, "").strip() if api_key_env else ""
    if api_key:
        return api_key
    return _load_api_key_file(config)


def _load_api_key_file(config: ChatConfig) -> str:
    raw_path = str(config.ai_settings.get("api_key_file", "")).strip()
    if not raw_path:
        return ""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = config.project_root / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(payload, Mapping):
        return ""
    for key in ("deepseek_api_key", "api_key", "key"):
        value = _optional_str(payload.get(key))
        if value:
            return value
    return ""


def _optional_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_deepseek_messages(payload: AIRequestPayload) -> list[dict[str, str]]:
    json_contract = {
        "output": "只输出一个 JSON 对象 不要 Markdown 不要代码块 不要额外解释",
        "required_fields": [
            "schema_version",
            "text",
            "sticker_id",
            "action_id",
            "intent",
            "state_request",
        ],
        "fixed_values": {
            "schema_version": 1,
        },
        "defaults": {
            "sticker_id": None,
            "action_id": "say_self",
            "state_request": None,
            "intent": "chat",
        },
        "style": {
            "default_text_length": "1-2 句",
            "tone": "像朋友聊天 简短自然 不客服 不作文",
            "longer_reply_only_when": "用户提出复杂问题或需要具体解释",
        },
        "effect_limits": {
            "sticker_id": "默认 null 只有情绪非常明确且贴纸合适时才填写",
            "action_id": "每次回复都必须从 available_actions 中按语气四选一：say_self(自言自语)、say_serious(严肃说话)、say_shining(发光说话)、say_shy(害羞说话) 不能填 null",
            "state_request": "默认 null 只有用户明确需要可用物品时才使用 use_item",
        },
        "state_boundaries": {
            "pet_state": "真实养成状态 只读 不能请求修改",
            "visual_state": "表现状态 只读 只能理解 happy normal poor_condition ill",
            "any": "不是状态 只用于素材兜底 不能出现在回复状态请求里",
        },
        "forbidden": [
            "delete_chat_history",
            "delete_memory",
            "memory_update",
            "modify_memory",
            "modify_persona",
            "modify_user_profile",
            "modify_api_settings",
            "set_visual_state",
            "use_any_state",
        ],
        "user_profile_policy": {
            "address_user_as": "优先使用 user_profile.pet_call_user 缺失时使用 主人",
            "use_preferences": "按 user_profile.chat_preferences 调整长度 安慰方式 吐槽尺度 建议方式 emoji 和贴纸克制程度",
            "respect_boundaries": "遵守 user_profile.boundaries 不使用 never_call_user 里的称呼",
            "profile_is_read_only": "不能修改 user_profile 不能声称已经修改 user_profile",
        },
        "memory_policy": {
            "long_term_memory_is_read_only": "只能读取 long_term_memory 摘要 不能声称自己直接修改配置文件",
            "explicit_user_memory": "如果用户明确说 记住/记一下/帮我记住/以后记得 可以自然确认",
            "forbidden": "不能声称删除 清空 修改 user_profile pet_persona API 设置或历史路径",
        },
        "example": {
            "schema_version": 1,
            "text": "早呀，我在呢。",
            "sticker_id": None,
            "action_id": "say_self",
            "intent": "action_request",
            "state_request": None,
        },
    }
    system_payload = {
        "conversation_goal": payload.conversation_goal,
        "persona": dict(payload.persona),
        "style_rules": list(payload.style_rules),
        "allowed_state_requests": list(payload.allowed_state_requests),
        "forbidden_requests": list(payload.forbidden_requests),
        "response_schema": dict(payload.response_schema),
        "json_contract": json_contract,
        "user_profile_policy": json_contract["user_profile_policy"],
        "memory_policy": json_contract["memory_policy"],
    }
    user_payload = {
        "response_contract_reminder": {
            "must_include_all_fields": list(json_contract["required_fields"]),
            "schema_version": 1,
            "default_null_fields": ["sticker_id", "state_request"],
            "text_length": "默认 1-2 句 复杂问题才稍长",
            "user_profile_usage": "按 user_profile.pet_call_user 称呼用户 资料为空时称呼主人 不要声称修改用户资料",
            "memory_usage": "长期记忆只读；用户明确要求记住时可自然确认，但不要声称修改配置或删除记忆",
        },
        "time_context": dict(payload.time_context),
        "user_profile": dict(payload.user_profile),
        "pet_state": dict(payload.pet_state),
        "runtime_state": dict(payload.runtime_state),
        "visual_state": payload.visual_state,
        "inventory": [dict(item) for item in payload.inventory],
        "active_activity": payload.active_activity,
        "recent_messages": [dict(item) for item in payload.recent_messages],
        "long_term_memory": dict(payload.long_term_memory),
        "available_stickers": [dict(item) for item in payload.available_stickers],
        "available_actions": [dict(item) for item in payload.available_actions],
        "recent_ai_usage": dict(payload.recent_ai_usage),
        "user_message": dict(payload.user_message),
    }
    return [
        {
            "role": "system",
            "content": json.dumps(system_payload, ensure_ascii=False),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]


def _request_body(payload: AIRequestPayload, config: ChatConfig) -> dict[str, object]:
    return {
        "model": str(config.ai_settings.get("model", "deepseek-chat")),
        "messages": build_deepseek_messages(payload),
        "temperature": float(config.ai_settings.get("temperature", 0.7)),
        "max_tokens": int(config.ai_settings.get("max_tokens", 800)),
        "stream": False,
    }


def _urllib_post(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def _extract_content(response_text: str) -> str | None:
    try:
        payload = json.loads(response_text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        return None
    return content


__all__ = ["DeepSeekChatProvider", "build_deepseek_messages"]

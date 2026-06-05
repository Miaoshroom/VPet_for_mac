"""AI 回复 JSON 的安全解析器"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from core.chat.config import ChatConfig, load_chat_config
from core.chat.models import (
    AIIntent,
    AIReplyV1,
    EffectKind,
    EffectRequest,
    ParseResult,
    SCHEMA_VERSION,
)

ALLOWED_REPLY_FIELDS = {
    "schema_version",
    "text",
    "sticker_id",
    "action_id",
    "intent",
    "state_request",
}

FORBIDDEN_KEYS = {
    "delete_chat_history",
    "delete_memory",
    "memory_update",
    "modify_memory",
    "modify_persona",
    "modify_user_profile",
    "modify_api_settings",
    "modify_pet_state",
    "set_pet_state",
    "pet_state",
    "save_game",
    "modify_save_game",
    "money",
    "coins",
    "gold",
    "backpack",
    "inventory",
    "activity_progress",
    "visual_state",
}

FORBIDDEN_REQUEST_TYPES = {
    "delete_chat_history",
    "delete_memory",
    "memory_update",
    "modify_memory",
    "modify_persona",
    "modify_user_profile",
    "modify_api_settings",
    "modify_pet_state",
    "set_pet_state",
    "modify_save_game",
    "modify_money",
    "modify_inventory",
    "modify_activity_progress",
    "set_visual_state",
    "change_visual_state",
}

CODE_BLOCK_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class ReplyParser:
    def __init__(self, config: ChatConfig | None = None) -> None:
        self.config = config or load_chat_config()

    def parse(self, raw_text: str) -> ParseResult:
        warnings: list[str] = []
        payload_text = _strip_code_block(raw_text)
        try:
            payload = json.loads(payload_text)
        except ValueError:
            warnings.append("invalid_json_fallback")
            return _fallback(raw_text, warnings)
        if not isinstance(payload, dict):
            warnings.append("non_object_json_fallback")
            return _fallback(raw_text, warnings)

        safety_warnings = _safety_warnings(payload)
        warnings.extend(safety_warnings)

        extra_fields = sorted(set(payload) - ALLOWED_REPLY_FIELDS)
        for field in extra_fields:
            warnings.append(f"extra_field_dropped:{field}")

        if "schema_version" not in payload:
            warnings.append("schema_version_missing")
            schema_version = SCHEMA_VERSION
        else:
            schema_version = payload.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            warnings.append(f"schema_version_warning:{schema_version}")

        text = _clean_text(payload.get("text"))
        sticker_id = self._clean_sticker_id(payload.get("sticker_id"), warnings)
        action_id = self._clean_action_id(payload.get("action_id"), warnings)
        intent = _clean_intent(payload.get("intent"), warnings)
        state_request = self._clean_state_request(
            payload.get("state_request"), warnings
        )

        if safety_warnings:
            action_id = None
            state_request = None
            warnings.append("safety_warning:effects_blocked")

        effects: list[EffectRequest] = []
        if action_id is not None:
            effects.append(EffectRequest(kind=EffectKind.ACTION, action_id=action_id))
            intent = AIIntent.ACTION_REQUEST
        if state_request is not None:
            item_id = str(state_request["item_id"])
            effects.append(EffectRequest(kind=EffectKind.USE_ITEM, item_id=item_id))
            intent = AIIntent.USE_ITEM_REQUEST

        if not text and sticker_id is None:
            text = "我刚才有点走神了，可以再说一次吗？"
            intent = AIIntent.FALLBACK
            warnings.append("empty_reply_fallback")

        reply = AIReplyV1(
            text=text,
            sticker_id=sticker_id,
            action_id=action_id,
            intent=intent,
            state_request=state_request,
        )
        return ParseResult(
            reply=reply,
            effects=tuple(effects),
            warnings=_dedupe(warnings),
            raw_text=raw_text,
        )

    def _clean_sticker_id(self, value: Any, warnings: list[str]) -> str | None:
        sticker_id = _optional_str(value)
        if sticker_id is None:
            return None
        if sticker_id not in self.config.stickers:
            warnings.append(f"invalid_sticker_id_dropped:{sticker_id}")
            return None
        return sticker_id

    def _clean_action_id(self, value: Any, warnings: list[str]) -> str | None:
        action_id = _optional_str(value)
        if action_id is None:
            return None
        action = self.config.actions.get(action_id)
        if action is None:
            warnings.append(f"invalid_action_id_dropped:{action_id}")
            return None
        if not action.allow_in_v1:
            warnings.append(f"action_not_allowed_in_v1_dropped:{action_id}")
            return None
        return action_id

    def _clean_state_request(
        self, value: Any, warnings: list[str]
    ) -> dict[str, str] | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            warnings.append("invalid_state_request_dropped")
            return None
        safety_warnings = _safety_warnings(value)
        warnings.extend(safety_warnings)
        if safety_warnings:
            return None
        request_type = _optional_str(value.get("type"))
        if request_type != "use_item":
            warnings.append(f"state_request_rejected:{request_type}")
            return None
        extra_fields = sorted(set(value) - {"type", "item_id"})
        for field in extra_fields:
            warnings.append(f"state_request_extra_field_dropped:{field}")
        item_id = _optional_str(value.get("item_id"))
        if item_id is None:
            warnings.append("state_request_missing_item_id")
            return None
        if item_id not in self.config.allowed_use_item_ids:
            warnings.append(f"use_item_not_allowed_in_v1_dropped:{item_id}")
            return None
        return {"type": "use_item", "item_id": item_id}


def _strip_code_block(raw_text: str) -> str:
    match = CODE_BLOCK_RE.match(raw_text)
    if match:
        return match.group(1).strip()
    return raw_text.strip()


def _fallback(raw_text: str, warnings: list[str]) -> ParseResult:
    return ParseResult(
        reply=AIReplyV1(
            text="我刚才有点走神了，可以再说一次吗？",
            intent=AIIntent.FALLBACK,
        ),
        warnings=tuple(warnings),
        raw_text=raw_text,
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_intent(value: Any, warnings: list[str]) -> AIIntent:
    if value is None:
        return AIIntent.CHAT
    try:
        return AIIntent(str(value))
    except ValueError:
        warnings.append(f"invalid_intent_defaulted:{value}")
        return AIIntent.CHAT


def _safety_warnings(value: Any) -> list[str]:
    warnings: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for raw_key, raw_value in item.items():
                key = str(raw_key)
                if key in FORBIDDEN_KEYS:
                    warnings.append(f"safety_warning:forbidden_request_rejected:{key}")
                if key == "type" and str(raw_value) in FORBIDDEN_REQUEST_TYPES:
                    warnings.append(
                        f"safety_warning:forbidden_request_rejected:{raw_value}"
                    )
                if key in {"visual_state", "state"} and str(raw_value) == "any":
                    warnings.append(
                        "safety_warning:forbidden_request_rejected:any_state"
                    )
                visit(raw_value)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return warnings


def _dedupe(warnings: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    clean: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        clean.append(warning)
    return tuple(clean)


__all__ = ["ReplyParser"]

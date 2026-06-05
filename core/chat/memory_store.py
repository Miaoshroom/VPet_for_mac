"""长期记忆存储

长期记忆只允许用户或程序界面人工编辑。AI 请求只能读取裁剪后的摘要，
不能通过回复字段触发写入。
"""

from __future__ import annotations

import json
import os
import re
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.chat.config import ChatStoragePaths

EMPTY_LONG_TERM_MEMORY: dict[str, Any] = {
    "schema_version": 1,
    "updated_at": None,
    "relationship_summary": "",
    "user_preferences": [],
    "important_facts": [],
    "recurring_topics": [],
    "boundaries": [],
    "manual_notes": [],
    "daily_summaries": [],
}

LONG_TERM_MEMORY_SECTIONS: tuple[str, ...] = (
    "user_preferences",
    "important_facts",
    "recurring_topics",
    "boundaries",
    "manual_notes",
    "daily_summaries",
)
LONG_TERM_MEMORY_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "updated_at", "relationship_summary", *LONG_TERM_MEMORY_SECTIONS}
)
FORBIDDEN_MEMORY_TOP_LEVEL_KEYS = frozenset({"user_profile", "pet_persona"})
PROMPT_LIST_LIMITS: dict[str, tuple[int, int]] = {
    "user_preferences": (8, 120),
    "important_facts": (8, 120),
    "recurring_topics": (8, 100),
    "boundaries": (8, 120),
    "manual_notes": (6, 120),
    "daily_summaries": (3, 160),
}
PATH_RE = re.compile(
    r"((?:/Users|/private|/Volumes|/tmp|~)[^\s，。；,;]+|[A-Za-z]:\\[^\s，。；,;]+)"
)
MANUAL_NOTE_DEDUPE_PUNCTUATION_RE = re.compile(
    r"[\s，。！？；：、,.!?;:'\"“”‘’（）()\[\]【】]+"
)


@dataclass(slots=True, frozen=True)
class ManualMemoryWriteResult:
    status: str
    text: str = ""
    note: Mapping[str, Any] | None = None
    backup_path: Path | None = None


@dataclass(slots=True, frozen=True)
class ManualMemoryDeleteCandidate:
    id: str
    text: str
    index: int
    score: int

    def to_preview_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": _clip_prompt_text(self.text, 120),
            "score": self.score,
        }


@dataclass(slots=True, frozen=True)
class ManualMemoryDeleteResult:
    status: str
    deleted_count: int = 0
    deleted: tuple[ManualMemoryDeleteCandidate, ...] = ()
    backup_path: Path | None = None


class MemoryStore:
    def __init__(self, storage: ChatStoragePaths | Path) -> None:
        if isinstance(storage, ChatStoragePaths):
            self.memory_file = storage.long_term_memory_file
        else:
            self.memory_file = storage
        self.backup_dir = self.memory_file.parent / "backups"

    def load(self) -> dict[str, Any]:
        """Return the prompt-safe, read-only summary used by AI providers."""

        return self.prompt_summary(self.load_full())

    def load_full(self) -> dict[str, Any]:
        if not self.memory_file.exists():
            return dict(EMPTY_LONG_TERM_MEMORY)
        try:
            payload = json.loads(self.memory_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(EMPTY_LONG_TERM_MEMORY)
        if not isinstance(payload, dict):
            return dict(EMPTY_LONG_TERM_MEMORY)
        return normalize_long_term_memory(payload)

    def save_full(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str = "user",
    ) -> Path:
        """Validate and persist a full manual long-term-memory document."""

        if actor not in {"user", "program"}:
            raise ValueError("long_term_memory_write_requires_manual_actor")
        clean = normalize_long_term_memory(payload, strict=True)
        clean["updated_at"] = _now_iso()
        backup_path = self._create_backup()
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.memory_file.with_suffix(self.memory_file.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(clean, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, self.memory_file)
        return backup_path

    def update_section(
        self,
        section: str,
        value: Sequence[Any],
        *,
        actor: str = "user",
    ) -> Path:
        if section not in LONG_TERM_MEMORY_SECTIONS:
            raise ValueError(f"unknown_long_term_memory_section:{section}")
        payload = self.load_full()
        payload[section] = list(value)
        return self.save_full(payload, actor=actor)

    def append_manual_note(
        self,
        text: str,
        *,
        source_message_id: str,
        source: str = "user_explicit",
        tags: Sequence[str] = (),
        actor: str = "user",
    ) -> ManualMemoryWriteResult:
        """Append a user-authorized manual note with backup and de-duplication."""

        clean_text = _text_value(text)
        if not clean_text:
            return ManualMemoryWriteResult(status="ignored_empty")
        payload = self.load_full()
        notes = list(payload.get("manual_notes", []))
        dedupe_key = _manual_note_dedupe_key(clean_text)
        for item in notes:
            existing_text = _manual_note_text(item)
            if existing_text and _manual_note_dedupe_key(existing_text) == dedupe_key:
                return ManualMemoryWriteResult(
                    status="already_exists",
                    text=existing_text,
                    note=_manual_note_metadata(item),
                )

        now = _now_iso()
        note = {
            "id": f"manual_{_timestamp_slug()}",
            "created_at": now,
            "text": clean_text,
            "source": source,
            "source_message_id": str(source_message_id or ""),
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        }
        payload["manual_notes"] = [note, *notes]
        backup_path = self.save_full(payload, actor=actor)
        return ManualMemoryWriteResult(
            status="saved",
            text=clean_text,
            note=note,
            backup_path=backup_path,
        )

    def find_manual_notes(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> tuple[ManualMemoryDeleteCandidate, ...]:
        """Find likely manual-note deletion candidates without mutating storage."""

        clean_query = _text_value(query)
        if not clean_query:
            return ()
        query_key = _manual_note_search_key(clean_query)
        query_term = _manual_note_search_term(clean_query)
        if not query_key and not query_term:
            return ()
        candidates: list[ManualMemoryDeleteCandidate] = []
        for index, item in enumerate(self.load_full().get("manual_notes", [])):
            text = _manual_note_text(item)
            if not text:
                continue
            score = _manual_note_match_score(query_key, query_term, text)
            if score <= 0:
                continue
            candidates.append(
                ManualMemoryDeleteCandidate(
                    id=_manual_note_id(item, index),
                    text=text,
                    index=index,
                    score=score,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.index))
        return tuple(candidates[: max(1, int(limit))])

    def delete_manual_notes(
        self,
        ids: Sequence[str],
        *,
        actor: str = "user",
    ) -> ManualMemoryDeleteResult:
        """Delete manual notes by id, preserving all other long-term sections."""

        requested_ids = {str(item).strip() for item in ids if str(item).strip()}
        if not requested_ids:
            return ManualMemoryDeleteResult(status="ignored_empty")
        payload = self.load_full()
        notes = list(payload.get("manual_notes", []))
        kept: list[Any] = []
        deleted: list[ManualMemoryDeleteCandidate] = []
        for index, item in enumerate(notes):
            note_id = _manual_note_id(item, index)
            if note_id in requested_ids:
                deleted.append(
                    ManualMemoryDeleteCandidate(
                        id=note_id,
                        text=_manual_note_text(item),
                        index=index,
                        score=0,
                    )
                )
            else:
                kept.append(item)
        if not deleted:
            return ManualMemoryDeleteResult(status="not_found")
        payload["manual_notes"] = kept
        backup_path = self.save_full(payload, actor=actor)
        return ManualMemoryDeleteResult(
            status="deleted",
            deleted_count=len(deleted),
            deleted=tuple(deleted),
            backup_path=backup_path,
        )

    def prompt_summary(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        source = normalize_long_term_memory(payload or self.load_full())
        summary: dict[str, Any] = {
            "schema_version": 1,
            "updated_at": source.get("updated_at"),
            "read_only": True,
            "source": "long_term_memory",
            "scope_note": (
                "长期记忆是人工维护的对话记忆，不等于 pet_persona，也不等于 user_profile；"
                "AI 只能读取摘要，不能修改。"
            ),
            "relationship_summary": _clip_prompt_text(
                source.get("relationship_summary"),
                280,
            ),
        }
        for section in LONG_TERM_MEMORY_SECTIONS:
            max_items, max_len = PROMPT_LIST_LIMITS[section]
            summary[section] = [
                text
                for text in (
                    _clip_prompt_text(_prompt_section_item_text(section, item), max_len)
                    for item in source.get(section, [])[:max_items]
                )
                if text
            ]
        return summary

    def _create_backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self.backup_dir / f"long_term_memory-{_timestamp_slug()}.json"
        if self.memory_file.exists():
            try:
                backup_text = self.memory_file.read_text(encoding="utf-8")
            except OSError:
                backup_text = json.dumps(EMPTY_LONG_TERM_MEMORY, ensure_ascii=False, indent=2)
        else:
            backup_text = json.dumps(EMPTY_LONG_TERM_MEMORY, ensure_ascii=False, indent=2)
        backup_path.write_text(backup_text.rstrip() + "\n", encoding="utf-8")
        return backup_path


def normalize_long_term_memory(
    payload: Mapping[str, Any],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    if strict:
        unknown = sorted(set(payload) - LONG_TERM_MEMORY_TOP_LEVEL_KEYS)
        forbidden = sorted(set(payload) & FORBIDDEN_MEMORY_TOP_LEVEL_KEYS)
        if forbidden:
            raise ValueError(
                "long_term_memory_cannot_override:" + ",".join(forbidden)
            )
        if unknown:
            raise ValueError(
                "unknown_long_term_memory_fields:" + ",".join(unknown)
            )
        clean = dict(EMPTY_LONG_TERM_MEMORY)
    else:
        clean = dict(EMPTY_LONG_TERM_MEMORY)
        if "summary" in payload and "relationship_summary" not in payload:
            clean["relationship_summary"] = _text_value(payload.get("summary"))
        if "items" in payload and "manual_notes" not in payload:
            clean["manual_notes"] = _list_value(payload.get("items"))

    clean["schema_version"] = 1
    clean["updated_at"] = _optional_text(payload.get("updated_at"))
    clean["relationship_summary"] = _text_value(payload.get("relationship_summary", clean["relationship_summary"]))
    for section in LONG_TERM_MEMORY_SECTIONS:
        clean[section] = _list_value(payload.get(section, clean[section]))
    return clean


def _list_value(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    clean: list[Any] = []
    for item in value:
        if isinstance(item, str | int | float | bool) or item is None:
            clean.append(item)
        elif isinstance(item, Mapping):
            clean.append(_json_safe_mapping(item))
        else:
            clean.append(str(item))
    return clean


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if isinstance(raw_value, str | int | float | bool) or raw_value is None:
            clean[key] = raw_value
        elif isinstance(raw_value, Mapping):
            clean[key] = _json_safe_mapping(raw_value)
        elif isinstance(raw_value, list):
            clean[key] = _list_value(raw_value)
        else:
            clean[key] = str(raw_value)
    return clean


def _prompt_section_item_text(section: str, item: Any) -> Any:
    if section == "manual_notes":
        return _manual_note_text(item)
    return item


def _manual_note_text(item: Any) -> str:
    if isinstance(item, Mapping):
        return _text_value(item.get("text"))
    return _text_value(item)


def _manual_note_metadata(item: Any) -> Mapping[str, Any] | None:
    if isinstance(item, Mapping):
        return dict(item)
    text = _text_value(item)
    if text:
        return {"text": text}
    return None


def _manual_note_id(item: Any, index: int) -> str:
    if isinstance(item, Mapping):
        note_id = _text_value(item.get("id"))
        if note_id:
            return note_id
    digest = hashlib.sha1(_manual_note_text(item).encode("utf-8")).hexdigest()[:12]
    return f"legacy_{index}_{digest}"


def _manual_note_dedupe_key(text: str) -> str:
    return MANUAL_NOTE_DEDUPE_PUNCTUATION_RE.sub("", _text_value(text)).casefold()


def _manual_note_search_key(text: str) -> str:
    clean = _text_value(text)
    if clean.startswith("我的"):
        clean = "用户的" + clean[2:]
    elif clean.startswith("我"):
        clean = "用户" + clean[1:]
    return _manual_note_dedupe_key(clean)


def _manual_note_search_term(text: str) -> str:
    key = _manual_note_search_key(text)
    for token in (
        "用户不喜欢",
        "用户喜欢",
        "用户的",
        "用户",
        "不喜欢",
        "喜欢",
        "关于",
        "记忆",
        "这条",
        "这件事",
        "不要记得",
    ):
        key = key.replace(token, "")
    return key


def _manual_note_match_score(query_key: str, query_term: str, note_text: str) -> int:
    note_key = _manual_note_search_key(note_text)
    if not query_key or not note_key:
        return 0
    if note_key == query_key:
        return 100
    if query_key in note_key:
        return 80 + min(len(query_key), 20)
    if note_key in query_key:
        return 65 + min(len(note_key), 20)
    if query_term and len(query_term) >= 2 and query_term in note_key:
        return 45 + min(len(query_term), 20)
    return 0


def _clip_prompt_text(value: Any, max_len: int) -> str:
    text = _redact_internal_paths(_text_value(value))
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _redact_internal_paths(text: str) -> str:
    text = text.replace("chat_data/memory/backups", "[路径已隐藏]")
    text = text.replace("chat_data/memory", "[路径已隐藏]")
    return PATH_RE.sub("[路径已隐藏]", text)


def _text_value(value: Any) -> str:
    if isinstance(value, Mapping):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value or "")
    return " ".join(text.split())


def _optional_text(value: Any) -> str | None:
    text = _text_value(value)
    return text or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


__all__ = [
    "EMPTY_LONG_TERM_MEMORY",
    "LONG_TERM_MEMORY_SECTIONS",
    "ManualMemoryDeleteCandidate",
    "ManualMemoryDeleteResult",
    "ManualMemoryWriteResult",
    "MemoryStore",
    "normalize_long_term_memory",
]

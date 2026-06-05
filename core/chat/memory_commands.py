"""用户显式长期记忆命令解析"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

MIN_MEMORY_TEXT_LENGTH = 3
SENSITIVE_MEMORY_WARNING = "explicit_memory_sensitive_rejected"
EMPTY_MEMORY_WARNING = "explicit_memory_empty_or_too_short"
CLEAR_ALL_MEMORY_WARNING = "explicit_memory_delete_clear_all_rejected"
PROTECTED_MEMORY_TARGET_WARNING = "explicit_memory_delete_protected_target_rejected"
EMPTY_DELETE_QUERY_WARNING = "explicit_memory_delete_empty_query"

DELETE_MEMORY_COMMAND_RE = re.compile(
    r"^\s*(?:忘记|删除(?:这条)?记忆|清空记忆|删掉(?:这条)?记忆)\b"
)
CLEAR_ALL_MEMORY_RE = re.compile(
    r"^\s*(?:(?:清空|清除|删除|删掉).*(?:全部|所有).*(?:记忆|长期记忆)|"
    r"(?:清空|清除|删除|删掉)\s*(?:长期)?记忆)\s*$"
)
PROTECTED_MEMORY_TARGET_RE = re.compile(
    r"(user_profile|pet_persona|api\s*设置|api\s*settings|用户资料|宠物人格|人格文件|角色设定)",
    re.IGNORECASE,
)
SENSITIVE_CREDENTIAL_RE = re.compile(
    r"(api\s*[-_ ]?\s*key|token|password|passwd|bearer|sk-[A-Za-z0-9_-]*)",
    re.IGNORECASE,
)
EXPLICIT_MEMORY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(?:请|麻烦你?)?帮我记住\s*[：:，,、\s]*(?P<content>.*)$"),
    re.compile(r"^\s*(?:请|麻烦你?)?记住\s*[：:，,、\s]*(?P<content>.*)$"),
    re.compile(r"^\s*(?:请|麻烦你?)?记一下\s*[：:，,、\s]*(?P<content>.*)$"),
    re.compile(r"^\s*(?:请|麻烦你?)?以后记得\s*[：:，,、\s]*(?P<content>.*)$"),
    re.compile(
        r"^\s*这(?:一点|点|件事)?(?:请|麻烦你?)?帮我记住\s*[：:，,、\s]*(?P<content>.*)$"
    ),
)
EXPLICIT_MEMORY_DELETE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(?:请|麻烦你?)?忘记\s*[：:，,、\s]*(?P<query>.*)$"),
    re.compile(
        r"^\s*(?:请|麻烦你?)?(?:删掉|删除|清除)\s*关于\s*(?P<query>.*?)\s*的(?:长期)?记忆\s*$"
    ),
    re.compile(r"^\s*(?:请|麻烦你?)?不要记得\s*(?P<query>.*?)(?:了)?\s*$"),
    re.compile(
        r"^\s*(?:请|麻烦你?)?把\s*[“\"']?(?P<query>.*?)[”\"']?\s*从(?:长期)?记忆里(?:删掉|删除|清除)\s*$"
    ),
    re.compile(
        r"^\s*(?:请|麻烦你?)?清除\s*这条(?:长期)?记忆\s*[：:，,、\s]*(?P<query>.*)$"
    ),
)
SURROUNDING_PUNCTUATION = " \t\r\n：:，,。.!！?？；;、…"


@dataclass(slots=True, frozen=True)
class ExplicitMemoryCommand:
    status: str
    raw_content: str = ""
    note_text: str = ""
    warning: str | None = None

    @property
    def can_write(self) -> bool:
        return self.status == "valid" and bool(self.note_text)


@dataclass(slots=True, frozen=True)
class ExplicitMemoryDeleteCommand:
    status: str
    raw_query: str = ""
    query: str = ""
    warning: str | None = None

    @property
    def can_propose(self) -> bool:
        return self.status == "valid" and bool(self.query)


def parse_explicit_memory_command(text: str) -> ExplicitMemoryCommand | None:
    """Return a command only when the user explicitly asks to remember text."""

    message = str(text or "").strip()
    if not message or DELETE_MEMORY_COMMAND_RE.match(message):
        return None
    for pattern in EXPLICIT_MEMORY_PATTERNS:
        match = pattern.match(message)
        if match is None:
            continue
        content = _clean_memory_content(match.group("content"))
        if len(content) < MIN_MEMORY_TEXT_LENGTH:
            return ExplicitMemoryCommand(
                status="ignored_empty",
                raw_content=content,
                warning=EMPTY_MEMORY_WARNING,
            )
        if SENSITIVE_CREDENTIAL_RE.search(content):
            LOGGER.warning("拒绝写入显式长期记忆：内容疑似包含敏感凭据")
            return ExplicitMemoryCommand(
                status="rejected_sensitive",
                raw_content="",
                warning=SENSITIVE_MEMORY_WARNING,
            )
        return ExplicitMemoryCommand(
            status="valid",
            raw_content=content,
            note_text=_to_user_note_text(content),
        )
    return None


def parse_explicit_memory_delete_command(
    text: str,
) -> ExplicitMemoryDeleteCommand | None:
    """Return a deletion proposal command without performing any deletion."""

    message = str(text or "").strip()
    if not message:
        return None
    if CLEAR_ALL_MEMORY_RE.match(message):
        return ExplicitMemoryDeleteCommand(
            status="rejected_clear_all",
            warning=CLEAR_ALL_MEMORY_WARNING,
        )
    for pattern in EXPLICIT_MEMORY_DELETE_PATTERNS:
        match = pattern.match(message)
        if match is None:
            continue
        raw_query = _clean_memory_content(match.group("query"))
        if PROTECTED_MEMORY_TARGET_RE.search(raw_query):
            return ExplicitMemoryDeleteCommand(
                status="rejected_protected_target",
                raw_query="",
                warning=PROTECTED_MEMORY_TARGET_WARNING,
            )
        query = _to_user_note_text(_strip_delete_tail(raw_query))
        if len(query) < MIN_MEMORY_TEXT_LENGTH:
            return ExplicitMemoryDeleteCommand(
                status="ignored_empty",
                raw_query=raw_query,
                warning=EMPTY_DELETE_QUERY_WARNING,
            )
        return ExplicitMemoryDeleteCommand(
            status="valid",
            raw_query=raw_query,
            query=query,
        )
    return None


def _clean_memory_content(value: str) -> str:
    text = " ".join(str(value or "").split())
    return text.strip(SURROUNDING_PUNCTUATION)


def _strip_delete_tail(value: str) -> str:
    text = _clean_memory_content(value)
    return re.sub(r"(?:这件事|这条)?(?:了|啦|吧)?$", "", text).strip(SURROUNDING_PUNCTUATION)


def _to_user_note_text(content: str) -> str:
    text = _clean_memory_content(content)
    if text.startswith("我的"):
        return "用户的" + text[2:]
    if text.startswith("我"):
        return "用户" + text[1:]
    if text.startswith("本人"):
        return "用户" + text[2:]
    return text


__all__ = [
    "CLEAR_ALL_MEMORY_WARNING",
    "EMPTY_MEMORY_WARNING",
    "EMPTY_DELETE_QUERY_WARNING",
    "ExplicitMemoryCommand",
    "ExplicitMemoryDeleteCommand",
    "PROTECTED_MEMORY_TARGET_WARNING",
    "SENSITIVE_MEMORY_WARNING",
    "parse_explicit_memory_command",
    "parse_explicit_memory_delete_command",
]

"""JSONL 聊天历史存储"""

from __future__ import annotations

import json
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from core.chat.config import ChatStoragePaths
from core.chat.models import ChatMessage


class HistoryStore:
    def __init__(self, storage: ChatStoragePaths | Path) -> None:
        if isinstance(storage, ChatStoragePaths):
            self.history_dir = storage.history_dir
        else:
            self.history_dir = storage
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def append(self, message: ChatMessage) -> Path:
        path = self._day_path(_message_date(message))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(message.to_dict(), ensure_ascii=False))
            fh.write("\n")
        return path

    def load_day(
        self,
        day: date | str,
        *,
        limit: int | None = None,
    ) -> list[ChatMessage]:
        path = self._day_path(_coerce_date(day))
        if not path.exists():
            return []
        if limit is not None and limit <= 0:
            return []
        lines: Iterable[str]
        if limit is None:
            lines = path.read_text(encoding="utf-8").splitlines()
        else:
            lines = deque(_history_lines(path), maxlen=limit)
        messages: list[ChatMessage] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict):
                messages.append(ChatMessage.from_dict(payload))
        return messages

    def load_recent(
        self,
        *,
        days: int = 7,
        limit: int = 40,
        today: date | None = None,
    ) -> list[ChatMessage]:
        if days <= 0 or limit <= 0:
            return []
        today = today or date.today()
        collected: list[ChatMessage] = []
        for offset in range(days - 1, -1, -1):
            collected.extend(self.load_day(today - timedelta(days=offset)))
        return collected[-limit:]

    def available_days(self) -> list[date]:
        days: list[date] = []
        for path in self.history_dir.glob("*.jsonl"):
            try:
                days.append(date.fromisoformat(path.stem))
            except ValueError:
                continue
        return sorted(days)

    def latest_day(self) -> date | None:
        days = self.available_days()
        if not days:
            return None
        return days[-1]

    def previous_day_before(self, day: date | str) -> date | None:
        target = _coerce_date(day)
        for candidate in reversed(self.available_days()):
            if candidate < target:
                return candidate
        return None

    def append_many(self, messages: Iterable[ChatMessage]) -> None:
        for message in messages:
            self.append(message)

    def _day_path(self, day: date) -> Path:
        return self.history_dir / f"{day.isoformat()}.jsonl"


def _message_date(message: ChatMessage) -> date:
    return _coerce_date(message.timestamp[:10])


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return datetime.now().date()


def _history_lines(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8") as fh:
        yield from fh


__all__ = ["HistoryStore"]

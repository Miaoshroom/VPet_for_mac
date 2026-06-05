"""用于解析器和服务验证的离线假提供方"""

from __future__ import annotations

import json
from typing import Any, Mapping

from core.chat.models import AIRequestPayload, ProviderResult


class FakeChatProvider:
    def __init__(
        self,
        *,
        response: Mapping[str, Any] | str | None = None,
        invalid_json: bool = False,
        fail: bool = False,
        provider_name: str = "fake",
    ) -> None:
        self.response = response
        self.invalid_json = invalid_json
        self.fail = fail
        self.provider_name = provider_name

    def complete(self, payload: AIRequestPayload) -> ProviderResult:
        if self.fail:
            return ProviderResult(
                ok=False,
                content="",
                provider=self.provider_name,
                error="fake_provider_failure",
            )
        if self.invalid_json:
            return ProviderResult(
                ok=True,
                content="not json from fake provider",
                provider=self.provider_name,
            )
        if isinstance(self.response, str):
            content = self.response
        else:
            response = self.response or {
                "schema_version": 1,
                "text": "我在，这里先走离线回应。",
                "sticker_id": None,
                "action_id": None,
                "intent": "chat",
                "state_request": None,
            }
            content = json.dumps(response, ensure_ascii=False)
        return ProviderResult(ok=True, content=content, provider=self.provider_name)


__all__ = ["FakeChatProvider"]

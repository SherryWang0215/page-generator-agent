from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import settings


class LLMGenerationError(RuntimeError):
    """Raised when LLM generation fails."""


logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    def __init__(self) -> None:
        self.base_url = settings.openai_base_url.rstrip("/")
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.timeout = settings.llm_timeout_seconds

    @property
    def enabled(self) -> bool:
        return settings.llm_enabled

    def generate_json(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled or not self.api_key:
            raise LLMGenerationError("llm is not configured")

        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        payload = {
            "model": self.model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }

        logger.info(
            "LLM request started | base_url=%s | model=%s | payload=%s",
            self.base_url,
            self.model,
            json.dumps(payload, ensure_ascii=False),
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("LLM request failed")
            raise LLMGenerationError("llm request failed") from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            logger.exception("LLM response payload is invalid | raw_response=%s", response.text)
            raise LLMGenerationError("llm response payload is invalid") from exc

        logger.info(
            "LLM response received | model=%s | content=%s",
            self.model,
            content,
        )

        try:
            return json.loads(extract_json_block(content))
        except json.JSONDecodeError as exc:
            logger.exception("LLM did not return valid json | content=%s", content)
            raise LLMGenerationError("llm did not return valid json") from exc


def extract_json_block(text: str) -> str:
    trimmed = text.strip()
    if trimmed.startswith("```"):
        lines = trimmed.splitlines()
        if len(lines) >= 3:
            trimmed = "\n".join(lines[1:-1]).strip()

    first_brace = trimmed.find("{")
    last_brace = trimmed.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        return trimmed
    return trimmed[first_brace : last_brace + 1]

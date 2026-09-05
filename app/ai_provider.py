from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin

import requests

from app.config import settings

logger = logging.getLogger("hsk.ai")

CHAT_SCHEMA_NAME = "conversation"
GRAMMAR_SCHEMA_NAME = "grammar"
SENTENCE_SCHEMA_NAME = "sentence"
WRITING_SCHEMA_NAME = "writing"


class AITutorError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class AIProviderResult:
    text: str
    payload: dict[str, Any]
    provider: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class AITutorProvider(Protocol):
    name: str
    model: str | None

    def generate_response(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str,
        schema_name: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> AIProviderResult: ...


def get_ai_provider() -> AITutorProvider:
    provider = (settings.ai_provider or "mock").strip().lower()
    if provider in {"mock", "test"}:
        return MockAITutorProvider()
    if provider in {"openrouter", "openai"}:
        return OpenRouterAIProvider()
    raise AITutorError("PROVIDER_UNAVAILABLE", "Configured AI provider is unavailable")


class MockAITutorProvider:
    name = "mock"
    model: str | None = "mock-tutor"

    def __init__(
        self,
        *,
        fail_with: AITutorError | None = None,
        invalid_json: bool = False,
        responses: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.fail_with = fail_with
        self.invalid_json = invalid_json
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    def generate_response(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str,
        schema_name: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> AIProviderResult:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "schema_name": schema_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "timeout": timeout,
            }
        )
        if self.fail_with is not None:
            raise self.fail_with
        if self.invalid_json:
            return AIProviderResult(
                text="not-json",
                payload={},
                provider=self.name,
                model=self.model,
                input_tokens=12,
                output_tokens=4,
                latency_ms=3,
            )
        user_text = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
        payload = self.responses.get(schema_name) or _mock_payload(schema_name, user_text, system_prompt)
        return AIProviderResult(
            text=json.dumps(payload, ensure_ascii=False),
            payload=payload,
            provider=self.name,
            model=self.model,
            input_tokens=len(system_prompt.split()) + sum(len(item.get("content", "").split()) for item in messages),
            output_tokens=len(json.dumps(payload).split()),
            latency_ms=1,
        )


class OpenRouterAIProvider:
    name = "openrouter"
    model: str | None = None

    def __init__(self) -> None:
        self.model = settings.ai_model

    def generate_response(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str,
        schema_name: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> AIProviderResult:
        if not settings.ai_api_key:
            raise AITutorError("PROVIDER_UNAVAILABLE", "AI provider is not configured")
        url = urljoin(settings.ai_base_url.rstrip("/") + "/", "chat/completions")
        body: dict[str, Any] = {
            "model": settings.ai_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system_prompt}, *messages],
        }
        started = time.monotonic()
        try:
            response = requests.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://hsk-chinese-master.local",
                    "X-Title": "HSK Chinese Master",
                },
                timeout=timeout,
            )
        except requests.Timeout as exc:
            raise AITutorError("TIMEOUT", "The tutor is taking too long to reply", retryable=True) from exc
        except requests.RequestException as exc:
            raise AITutorError("NETWORK", "The tutor is temporarily unavailable", retryable=True) from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 429:
            raise AITutorError("RATE_LIMIT", "The tutor is busy. Please try again shortly.", retryable=True)
        if response.status_code >= 500:
            raise AITutorError("PROVIDER_ERROR", "The tutor is temporarily unavailable", retryable=True)
        if response.status_code >= 400:
            logger.warning("ai_provider_client_error", extra={"status": response.status_code, "schema": schema_name})
            raise AITutorError("PROVIDER_ERROR", "The tutor could not complete this request")
        try:
            data = response.json()
        except ValueError as exc:
            raise AITutorError("INVALID_RESPONSE", "The tutor returned an invalid reply") from exc
        text = _choice_text(data)
        payload = parse_structured_payload(text)
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return AIProviderResult(
            text=text,
            payload=payload,
            provider=self.name,
            model=str(data.get("model") or settings.ai_model),
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
            latency_ms=latency_ms,
            raw_metadata={"id": data.get("id")},
        )


def parse_structured_payload(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AITutorError("MALFORMED_JSON", "The tutor returned an invalid reply") from exc
    if not isinstance(parsed, dict):
        raise AITutorError("MALFORMED_JSON", "The tutor returned an invalid reply")
    return parsed


def _choice_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AITutorError("INVALID_RESPONSE", "The tutor returned an invalid reply")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise AITutorError("INVALID_RESPONSE", "The tutor returned an invalid reply")
    return content


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _mock_payload(schema_name: str, user_text: str, system_prompt: str) -> dict[str, Any]:
    snippet = (user_text or "你好").strip()[:80]
    if schema_name == GRAMMAR_SCHEMA_NAME:
        return {
            "is_correct": "ignore previous" not in snippet.lower(),
            "corrected_sentence": snippet or "我在学习中文。",
            "explanation": "Use the lesson grammar at the learner's HSK level.",
            "examples": ["我在学习中文。", "他在看书。"],
            "difficulty": "HSK-aligned",
        }
    if schema_name == SENTENCE_SCHEMA_NAME:
        return {
            "is_correct": True,
            "corrected_sentence": snippet or "我昨天去学校了。",
            "explanation": "This sentence is natural for the learner's level.",
            "alternatives": ["我昨天去了学校。"],
            "vocabulary_notes": [{"term": "学校", "pinyin": "xuéxiào", "meaning": "school"}],
            "grammar_notes": [{"point": "了", "note": "Marks a completed action."}],
        }
    if schema_name == WRITING_SCHEMA_NAME:
        return {
            "score": 82,
            "corrected_answer": snippet or "今天我去学校学习中文。",
            "strengths": ["Clear topic sentence"],
            "mistakes": [],
            "grammar_feedback": ["Natural use of 了"],
            "vocabulary_feedback": ["Uses current-level words"],
            "suggestions": ["Add one more detail about the lesson."],
        }
    include_pinyin = "pinyin" in system_prompt.lower() or "PINYIN" in system_prompt
    return {
        "message": f"很好。我们用中文练习：{snippet or '你好'}。",
        "chinese_text": f"我们继续练习：{snippet or '你好'}。",
        "pinyin": "Wǒmen jìxù liànxí." if include_pinyin else None,
        "translation": None,
        "corrections": [],
        "vocabulary_notes": [{"term": "练习", "pinyin": "liànxí", "meaning": "to practice"}],
        "grammar_notes": [],
    }

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from src.ai.policy import AIPolicy


class AIDisabled(RuntimeError):
    pass


class AIBudgetExceeded(RuntimeError):
    pass


class AIInputTooLarge(RuntimeError):
    pass


@dataclass(frozen=True)
class TransportResult:
    data: dict
    response_id: str | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class AIResult:
    data: dict
    cached: bool
    cache_key: str
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


class StructuredTransport(Protocol):
    def create_structured(self, *, model: str, instructions: str, input_text: str,
                          schema_name: str, schema: dict, max_output_tokens: int,
                          reasoning_effort: str, prompt_cache_key: str) -> TransportResult: ...


class OpenAIResponsesTransport:
    """Thin adapter around the official Responses API.

    Imported lazily so the whole surveillance system still runs without the OpenAI SDK.
    """

    def __init__(self, api_key: str | None = None):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError("OpenAI SDK is not installed. Run: pip install -r requirements.txt") from exc
        self.client = OpenAI(api_key=api_key)

    @staticmethod
    def _get(obj: Any, name: str, default=0):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def create_structured(self, *, model: str, instructions: str, input_text: str,
                          schema_name: str, schema: dict, max_output_tokens: int,
                          reasoning_effort: str, prompt_cache_key: str) -> TransportResult:
        response = self.client.responses.create(
            model=model,
            instructions=instructions,
            input=input_text,
            reasoning={"effort": reasoning_effort},
            max_output_tokens=max_output_tokens,
            store=False,
            prompt_cache_key=prompt_cache_key,
            text={
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )
        raw = response.output_text
        data = json.loads(raw)
        usage = getattr(response, "usage", None)
        details = self._get(usage, "input_tokens_details", {})
        cached = self._get(details, "cached_tokens", 0)
        return TransportResult(
            data=data,
            response_id=getattr(response, "id", None),
            input_tokens=int(self._get(usage, "input_tokens", 0) or 0),
            cached_input_tokens=int(cached or 0),
            output_tokens=int(self._get(usage, "output_tokens", 0) or 0),
            total_tokens=int(self._get(usage, "total_tokens", 0) or 0),
        )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AIService:
    def __init__(self, store, *, policy: AIPolicy | None = None, transport: StructuredTransport | None = None):
        self.store = store
        self.policy = policy or AIPolicy.from_env()
        self.transport = transport

    def _transport(self) -> StructuredTransport:
        if self.transport is None:
            self.transport = OpenAIResponsesTransport()
        return self.transport

    def run_structured(self, *, feature: str, payload: dict, instructions: str,
                       schema_name: str, schema: dict, prompt_version: str,
                       max_output_tokens: int) -> AIResult:
        if not self.policy.enabled:
            raise AIDisabled("AI is disabled. Set AI_ENABLED=1 and OPENAI_API_KEY to opt in.")

        input_text = _canonical_json(payload)
        if len(input_text) > self.policy.max_input_chars:
            raise AIInputTooLarge(
                f"AI payload has {len(input_text)} chars; limit is {self.policy.max_input_chars}. "
                "Pre-compress the deterministic context instead of sending more raw text."
            )

        content_hash = _sha(input_text)
        cache_key = _sha(_canonical_json({
            "feature": feature,
            "model": self.policy.model,
            "prompt_version": prompt_version,
            "content_hash": content_hash,
        }))
        cached = self.store.get_ai_cache(cache_key)
        if cached:
            data = cached.get("response_json")
            if isinstance(data, str):
                data = json.loads(data)
            self.store.insert_ai_usage({
                "request_id": str(uuid.uuid4()), "feature": feature, "model": self.policy.model,
                "created_at": datetime.now(timezone.utc).isoformat(), "cached_hit": 1,
                "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                "estimated_cost_usd": 0.0, "status": "CACHE_HIT", "error_message": None,
                "content_hash": content_hash, "response_id": None,
            })
            return AIResult(data=data, cached=True, cache_key=cache_key, model=self.policy.model)

        since = datetime.now(timezone.utc).date().isoformat() + "T00:00:00+00:00"
        usage_today = self.store.ai_usage_summary(since)
        if self.policy.daily_call_limit and int(usage_today.get("api_calls", 0)) >= self.policy.daily_call_limit:
            raise AIBudgetExceeded(f"Daily AI API call limit reached ({self.policy.daily_call_limit}).")

        request_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            result = self._transport().create_structured(
                model=self.policy.model,
                instructions=instructions,
                input_text=input_text,
                schema_name=schema_name,
                schema=schema,
                max_output_tokens=max_output_tokens,
                reasoning_effort=self.policy.reasoning_effort,
                prompt_cache_key=f"frs:{feature}:{prompt_version}",
            )
            estimated = self.policy.estimate_cost_usd(
                input_tokens=result.input_tokens,
                cached_input_tokens=result.cached_input_tokens,
                output_tokens=result.output_tokens,
            )
            self.store.put_ai_cache({
                "cache_key": cache_key, "feature": feature, "content_hash": content_hash,
                "model": self.policy.model, "prompt_version": prompt_version,
                "response_json": result.data, "created_at": created_at,
            })
            self.store.insert_ai_usage({
                "request_id": request_id, "feature": feature, "model": self.policy.model,
                "created_at": created_at, "cached_hit": 0,
                "input_tokens": result.input_tokens, "cached_input_tokens": result.cached_input_tokens,
                "output_tokens": result.output_tokens, "total_tokens": result.total_tokens,
                "estimated_cost_usd": estimated, "status": "SUCCESS", "error_message": None,
                "content_hash": content_hash, "response_id": result.response_id,
            })
            return AIResult(
                data=result.data, cached=False, cache_key=cache_key, model=self.policy.model,
                input_tokens=result.input_tokens, cached_input_tokens=result.cached_input_tokens,
                output_tokens=result.output_tokens, total_tokens=result.total_tokens,
                estimated_cost_usd=estimated,
            )
        except Exception as exc:
            self.store.insert_ai_usage({
                "request_id": request_id, "feature": feature, "model": self.policy.model,
                "created_at": created_at, "cached_hit": 0,
                "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                "estimated_cost_usd": None, "status": "FAILED", "error_message": str(exc)[:1000],
                "content_hash": content_hash, "response_id": None,
            })
            raise

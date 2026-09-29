from __future__ import annotations

import os
from dataclasses import dataclass

from src.config.env import load_dotenv


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AIPolicy:
    enabled: bool
    model: str
    daily_call_limit: int
    max_input_chars: int
    investigation_max_output_tokens: int
    disclosure_max_output_tokens: int
    reasoning_effort: str
    input_usd_per_mtok: float
    cached_input_usd_per_mtok: float
    output_usd_per_mtok: float

    @classmethod
    def from_env(cls) -> "AIPolicy":
        load_dotenv()
        # Explicit opt-in: a key alone never turns paid API calls on.
        enabled = _truthy(os.getenv("AI_ENABLED")) and bool(os.getenv("OPENAI_API_KEY", "").strip())
        return cls(
            enabled=enabled,
            model=os.getenv("AI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna",
            daily_call_limit=max(0, _int_env("AI_DAILY_CALL_LIMIT", 20)),
            max_input_chars=max(1000, _int_env("AI_MAX_INPUT_CHARS", 12000)),
            investigation_max_output_tokens=max(100, _int_env("AI_INVESTIGATION_MAX_OUTPUT_TOKENS", 450)),
            disclosure_max_output_tokens=max(80, _int_env("AI_DISCLOSURE_MAX_OUTPUT_TOKENS", 220)),
            reasoning_effort=os.getenv("AI_REASONING_EFFORT", "none").strip() or "none",
            # Pricing changes. Keep rates configurable rather than silently baking stale prices into audit logs.
            input_usd_per_mtok=max(0.0, _float_env("AI_INPUT_USD_PER_MTOK", 0.0)),
            cached_input_usd_per_mtok=max(0.0, _float_env("AI_CACHED_INPUT_USD_PER_MTOK", 0.0)),
            output_usd_per_mtok=max(0.0, _float_env("AI_OUTPUT_USD_PER_MTOK", 0.0)),
        )

    def estimate_cost_usd(self, *, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float | None:
        if not any((self.input_usd_per_mtok, self.cached_input_usd_per_mtok, self.output_usd_per_mtok)):
            return None
        non_cached = max(int(input_tokens) - int(cached_input_tokens), 0)
        return (
            non_cached * self.input_usd_per_mtok
            + int(cached_input_tokens) * self.cached_input_usd_per_mtok
            + int(output_tokens) * self.output_usd_per_mtok
        ) / 1_000_000.0

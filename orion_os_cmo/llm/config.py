"""LLM configuration loaded from environment variables.

Provides a single ``LLMConfig`` dataclass that can be constructed from
env vars, following the same pattern as ``TransportConfig``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    api_url: str
    api_key: str
    model: str
    max_tokens: int

    @classmethod
    def from_env(cls) -> LLMConfig:
        return cls(
            api_url=os.environ.get("LLM_API_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("LLM_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", "gpt-4o"),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4096")),
        )

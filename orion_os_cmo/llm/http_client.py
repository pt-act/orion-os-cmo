"""Client-agnostic ``LLMClient`` implementation over HTTP.

Implements the ``LLMClient`` protocol (structural typing — no explicit
inheritance) using stdlib ``urllib.request`` against any OpenAI-compatible
Chat Completions API. Configured via env vars (see ``LLMConfig``).

Usage:
    client = HttpLLMClient(LLMConfig.from_env())
    text = client.complete(system="You are...", prompt="Write...")
    data = client.complete_json(system="You are...", prompt="JSON output...")
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import LLMConfig


class LLMError(Exception):
    """Raised on transport/parse failure during LLM completion."""


class HttpLLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    def complete(self, *, system: str, prompt: str) -> str:
        resp = self._post(self._build_body(system, prompt))
        return self._extract_text(resp)

    def complete_json(self, *, system: str, prompt: str) -> dict[str, Any]:
        body = self._build_body(system, prompt)
        body["response_format"] = {"type": "json_object"}
        resp = self._post(body)
        content = self._extract_text(resp)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON parse failed: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LLMError(f"expected JSON object, got {type(parsed).__name__}")
        return parsed

    # ── internal ────────────────────────────────────────────────────────────

    def _build_body(self, system: str, prompt: str) -> dict[str, Any]:
        return {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self._config.max_tokens,
        }

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._config.api_url.rstrip('/')}/chat/completions"
        data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"transport: {exc.reason}") from exc
        except OSError as exc:
            raise LLMError(f"io: {exc}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"response not JSON: {exc}") from exc

    @staticmethod
    def _extract_text(resp: dict[str, Any]) -> str:
        choices = resp.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError("response: missing choices")
        msg = choices[0].get("message")
        if not isinstance(msg, dict):
            raise LLMError("response: missing message in choice")
        content = msg.get("content")
        if not isinstance(content, str):
            raise LLMError("response: missing content in message")
        return content

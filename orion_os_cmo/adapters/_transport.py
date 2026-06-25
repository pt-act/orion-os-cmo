"""Shared transport protocol for every adapter façade.

The payment/HTTP/OAuth transport (AgentCash x402, GitHub token, Google OAuth)
lives behind this boundary so no agent worker ever sees a key. Concrete
transports are injected at harness boot; tests inject a mock. This mirrors the
shape first established in ``adapters/crawl/types.py``.
"""

from __future__ import annotations

from typing import Any, Protocol


class Transport(Protocol):
    def post(self, path: str, body: dict[str, Any]) -> Any: ...

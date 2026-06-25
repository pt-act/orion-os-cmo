"""Pluggable LLM interface.

Agents depend on this Protocol, not on any specific provider. The default
implementation will be Claude (frontier, for the weekly pass); routing to another
provider is a swap of the concrete client, with no change to agent code.
"""

from __future__ import annotations

from typing import Any, Protocol


class LLMError(Exception):
    """Raised by a concrete LLM client when a completion cannot be produced."""


class LLMClient(Protocol):
    def complete_json(self, *, system: str, prompt: str) -> dict[str, Any]:
        """Return the model's response parsed as a single JSON object.

        Implementations are responsible for requesting JSON output and parsing
        it. They raise ``LLMError`` on transport/parse failure.
        """
        ...

    def complete(self, *, system: str, prompt: str) -> str:
        """Return the model's response as plain text.

        Used by agents that draft free-form copy (e.g. one community reply)
        rather than a structured object. Raises ``LLMError`` on failure.
        """
        ...

"""Typed contracts for the AgentCash Firecrawl/Exa crawl façade.

Satisfies H-1 (self-describing), H-2 (structured output), H-3 (atomic/idempotent).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol, TypeVar

from ...common.result import Err, Ok, Result as _Result

__all__ = [
    "ScrapeResult", "SearchHit", "SearchResult", "CrawlErrorKind",
    "ErrorSource", "CrawlError", "Transport", "Ok", "Err", "Result",
]


@dataclass(frozen=True)
class ScrapeResult:
    url: str  # final URL after redirects
    title: str  # may be empty
    content: str  # page content as markdown


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    text: str  # extracted page text, when available
    summary: Optional[str] = None
    score: Optional[float] = None


@dataclass(frozen=True)
class SearchResult:
    results: list[SearchHit]


CrawlErrorKind = Literal["transport", "invalid_response", "empty"]


@dataclass(frozen=True)
class ErrorSource:
    tool: str
    url: Optional[str] = None
    query: Optional[str] = None


@dataclass(frozen=True)
class CrawlError:
    """Structured failure (H-2) — never a silent empty result."""

    kind: CrawlErrorKind
    message: str
    source: ErrorSource


class Transport(Protocol):
    """Where a retrieval call sends requests.

    Injected so the payment/HTTP transport (AgentCash x402) stays behind the
    adapter boundary — the worker never sees a key — and tests can mock it.
    """

    def post(self, path: str, body: dict[str, Any]) -> Any: ...


_T = TypeVar("_T")
# Crawl-specific one-parameter alias over the shared Result (error is CrawlError).
Result = _Result[_T, CrawlError]

"""Thin façade over the AgentCash stableenrich.dev Firecrawl/Exa endpoints.

Each method is atomic and idempotent (H-3) and returns a structured ``Result``
(H-2). Provider/payment specifics live in the injected ``Transport``, not here.
"""

from __future__ import annotations

from typing import Any

from .types import (
    CrawlError,
    Err,
    ErrorSource,
    Ok,
    Result,
    ScrapeResult,
    SearchHit,
    SearchResult,
    Transport,
)

SCRAPE_PATH = "/api/firecrawl/scrape"
SEARCH_PATH = "/api/exa/search"


class CrawlAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def scrape(self, url: str) -> Result[ScrapeResult]:
        """Scrape a single URL to markdown (Firecrawl)."""
        try:
            raw = self._transport.post(SCRAPE_PATH, {"url": url})
        except Exception as exc:  # transport failure → structured error
            return Err(CrawlError("transport", str(exc), ErrorSource("firecrawl/scrape", url=url)))

        if not isinstance(raw, dict):
            return Err(CrawlError("invalid_response", "scrape response was not an object",
                                  ErrorSource("firecrawl/scrape", url=url)))

        content = raw.get("content")
        final_url = raw.get("url")
        title = raw.get("title")
        if not isinstance(content, str) or not isinstance(final_url, str):
            return Err(CrawlError("invalid_response", "scrape response missing url/content",
                                  ErrorSource("firecrawl/scrape", url=url)))
        if content.strip() == "":
            return Err(CrawlError("empty", "scrape returned empty content",
                                  ErrorSource("firecrawl/scrape", url=final_url)))

        return Ok(ScrapeResult(url=final_url, title=title if isinstance(title, str) else "", content=content))

    def search(self, query: str, num_results: int = 5) -> Result[SearchResult]:
        """Neural web search for competitor/market evidence (Exa)."""
        try:
            raw = self._transport.post(SEARCH_PATH, {
                "query": query,
                "numResults": num_results,
                "type": "auto",
                "contents": {"text": True, "summary": {}},
            })
        except Exception as exc:
            return Err(CrawlError("transport", str(exc), ErrorSource("exa/search", query=query)))

        if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
            return Err(CrawlError("invalid_response", "search response missing results[]",
                                  ErrorSource("exa/search", query=query)))

        hits: list[SearchHit] = []
        for item in raw["results"]:
            if not isinstance(item, dict):
                continue
            summary = item.get("summary")
            score = item.get("score")
            hits.append(SearchHit(
                title=_as_str(item.get("title")),
                url=_as_str(item.get("url")),
                text=_as_str(item.get("text")) or _as_str(summary),
                summary=summary if isinstance(summary, str) else None,
                score=float(score) if isinstance(score, (int, float)) else None,
            ))
        return Ok(SearchResult(results=hits))


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""

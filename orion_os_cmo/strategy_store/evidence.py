"""Normalize crawl output into a source-tagged evidence set.

``source`` is the provenance contract: no item exists without one, which is what
lets strategy-store guarantee every downstream claim is grounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from ..adapters.crawl.types import ScrapeResult, SearchResult


@dataclass(frozen=True)
class EvidenceSource:
    tool: str
    url: str


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    kind: Literal["page", "search_result"]
    source: EvidenceSource
    text: str
    title: Optional[str] = None


@dataclass(frozen=True)
class EvidenceSet:
    built_at: str
    items: list[EvidenceItem]


def build_evidence_set(
    pages: list[ScrapeResult],
    searches: list[SearchResult],
) -> EvidenceSet:
    """Combine scraped pages and search results into one id-stable evidence set."""
    drafts: list[tuple[Literal["page", "search_result"], EvidenceSource, Optional[str], str]] = []

    for page in pages:
        drafts.append(("page", EvidenceSource("firecrawl/scrape", page.url), page.title or None, page.content))

    for search in searches:
        for hit in search.results:
            if hit.text.strip() == "":  # drop empty-text hits
                continue
            drafts.append(("search_result", EvidenceSource("exa/search", hit.url), hit.title or None, hit.text))

    items = [
        EvidenceItem(id=f"ev-{i}", kind=kind, source=source, title=title, text=text)
        for i, (kind, source, title, text) in enumerate(drafts)
    ]
    return EvidenceSet(built_at=datetime.now(timezone.utc).isoformat(), items=items)

"""strategy-store Group 1 — retrieve source-tagged evidence for the strategy build.

The site scrape is required: without it there is no strategy to build, so a
failed scrape returns the structured ``CrawlError`` rather than a silent empty
set (tasks 1.3/1.4). Competitor searches are best-effort — a failed search is
skipped, not fatal.
"""

from __future__ import annotations

from typing import Optional

from ..adapters.crawl.adapter import CrawlAdapter
from ..adapters.crawl.types import Ok, Result, SearchResult
from .evidence import EvidenceSet, build_evidence_set


def retrieve_evidence(
    adapter: CrawlAdapter,
    url: str,
    competitor_queries: Optional[list[str]] = None,
) -> Result[EvidenceSet]:
    page = adapter.scrape(url)
    if not page.ok:
        return page  # structured error propagates

    searches: list[SearchResult] = []
    for query in competitor_queries or []:
        res = adapter.search(query)
        if res.ok:
            searches.append(res.value)

    return Ok(build_evidence_set([page.value], searches))

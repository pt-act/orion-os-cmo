"""Harness-boot wiring (ADR #7): run the data adapters on the self-hosted Transport.

No adapter class changes — the swap is purely which Transport is injected at boot.
External spend collapses to model tokens; scrape/audit are local, search hits one
own-key provider directly.

    ORION_SEARCH_PROVIDER=brave ORION_SEARCH_API_KEY=... uv run python \
        examples/self_hosted_harness_boot.py https://example.com

Requires (only for a real run): a Chromium-capable Playwright install for scrape,
Node + Lighthouse for the audit, and an own-key search account for search. Each is
needed only for its own handler.
"""

from __future__ import annotations

import sys

from orion_os_cmo.adapters.crawl.adapter import CrawlAdapter
from orion_os_cmo.adapters.seo_audit.adapter import SeoAuditAdapter
from orion_os_cmo.transports import SelfHostedTransport, TransportConfig


def main(url: str) -> None:
    # One wiring choice at boot. Keys are read from env inside the Transport (H-1).
    transport = SelfHostedTransport(TransportConfig.from_env())

    # The adapters are constructed exactly as before — they neither know nor care
    # that the backend is now self-hosted rather than an aggregator.
    crawl = CrawlAdapter(transport)
    seo_audit = SeoAuditAdapter(transport)

    page = crawl.scrape(url)
    print("scrape:", "ok" if page.ok else f"err({page.error.kind})")

    audit = seo_audit.seo_audit(url)
    if audit.ok:
        print(f"audit: score={audit.value.score} issues={len(audit.value.issues)}")
    else:
        print(f"audit: err({audit.error.kind})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "https://example.com")

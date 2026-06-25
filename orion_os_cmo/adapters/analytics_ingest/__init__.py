"""Analytics-ingest adapter — GA4 + GSC + Core Web Vitals as one snapshot."""

from __future__ import annotations

from .adapter import AnalyticsAdapter, validate_snapshot
from .types import AnalyticsError, AnalyticsSnapshot, CoreWebVitals, PageStat

__all__ = [
    "AnalyticsAdapter",
    "validate_snapshot",
    "AnalyticsError",
    "AnalyticsSnapshot",
    "CoreWebVitals",
    "PageStat",
]

"""Typed contracts for the analytics-ingest façade (GA4 + GSC + CWV)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = [
    "PageStat", "CoreWebVitals", "AnalyticsSnapshot",
    "AnalyticsErrorKind", "ErrorSource", "AnalyticsError", "Transport",
]


@dataclass(frozen=True)
class PageStat:
    url: str
    sessions: int
    clicks: int
    impressions: int


@dataclass(frozen=True)
class CoreWebVitals:
    lcp_ms: float
    inp_ms: float
    cls: float


@dataclass(frozen=True)
class AnalyticsSnapshot:
    sessions: int
    clicks: int
    impressions: int
    top_pages: list[PageStat]
    core_web_vitals: CoreWebVitals
    meta: dict = field(default_factory=dict)  # property_id, date_range, fetched_at


AnalyticsErrorKind = Literal["not_connected", "auth_failure", "invalid_response", "transport"]


@dataclass(frozen=True)
class ErrorSource:
    api: str
    property_id: Optional[str] = None


@dataclass(frozen=True)
class AnalyticsError:
    kind: AnalyticsErrorKind
    message: str
    source: ErrorSource

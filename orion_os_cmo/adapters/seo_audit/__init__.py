"""SEO-audit adapter — on-page provider + Lighthouse into one AuditReport."""

from __future__ import annotations

from .adapter import SeoAuditAdapter, validate_report
from .types import AuditError, AuditReport, Issue, SerpEntry

__all__ = ["SeoAuditAdapter", "validate_report", "AuditError", "AuditReport", "Issue", "SerpEntry"]

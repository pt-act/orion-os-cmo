"""Typed contracts for agent-seo's ranked output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = ["RankedFix", "KeywordGap", "SeoFindings", "SeoAgentError"]

Severity = Literal["critical", "warning", "info"]


@dataclass(frozen=True)
class RankedFix:
    issue_id: str
    issue: str
    fix: str
    snippet: str
    severity: Severity
    rationale: str = ""


@dataclass(frozen=True)
class KeywordGap:
    query: str
    impressions: int
    source: Literal["gsc"] = "gsc"


@dataclass(frozen=True)
class SeoFindings:
    ranked_fixes: list[RankedFix]
    keyword_gaps: list[KeywordGap]
    meta: dict = field(default_factory=dict)  # url, audit_score, analytics_period, run_at


SeoAgentErrorKind = Literal[
    "strategy_missing", "audit_failed", "analytics_failed", "llm_error", "schema_invalid"
]


@dataclass(frozen=True)
class SeoAgentError:
    kind: SeoAgentErrorKind
    message: str

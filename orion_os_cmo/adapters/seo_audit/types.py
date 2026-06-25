"""Typed contracts for the seo-audit façade (on-page provider + Lighthouse)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = [
    "Issue", "SerpEntry", "AuditReport",
    "AuditErrorKind", "ErrorSource", "AuditError", "Transport",
]

Severity = Literal["critical", "warning", "info"]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    type: str
    fix: str
    snippet: str


@dataclass(frozen=True)
class SerpEntry:
    position: int
    title: str
    url: str


@dataclass(frozen=True)
class AuditReport:
    url: str
    score: int  # 0-100 normalized
    issues: list[Issue]
    serp_snapshot: list[SerpEntry]
    meta: dict = field(default_factory=dict)  # provider, lighthouse_version, audited_at


AuditErrorKind = Literal["transport", "invalid_response", "lighthouse_failure", "schema_invalid"]


@dataclass(frozen=True)
class ErrorSource:
    provider: str
    url: str


@dataclass(frozen=True)
class AuditError:
    kind: AuditErrorKind
    message: str
    source: ErrorSource

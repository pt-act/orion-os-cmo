"""Typed contracts for agent-geo's output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

__all__ = ["GapRef", "GeoFix", "GeoFindings", "GeoAgentError"]

FixType = Literal["faq", "json_ld", "entity_paragraph"]


@dataclass(frozen=True)
class GapRef:
    model: str
    question: str


@dataclass(frozen=True)
class GeoFix:
    fix: str
    snippet: str
    fix_type: FixType
    gap_ref: GapRef  # provenance: the probe gap this fixes


@dataclass(frozen=True)
class GeoFindings:
    score: float
    score_delta: Optional[float]
    fixes: list[GeoFix]
    competitor_gaps: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)  # run_at, probe_model_count, question_count, note?


GeoAgentErrorKind = Literal["strategy_missing", "llm_error", "schema_invalid"]


@dataclass(frozen=True)
class GeoAgentError:
    kind: GeoAgentErrorKind
    message: str

"""Typed contracts for the geo-probe façade (AI-answer-engine visibility)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = [
    "ModelResult", "GeoReport", "ProbeErrorKind", "ProbeErrorSource", "ProbeError", "Transport",
]

Sentiment = Literal["positive", "neutral", "negative", "none"]


@dataclass(frozen=True)
class ModelResult:
    model: str
    question: str
    mentioned: bool
    position: Optional[int]
    sentiment: Sentiment
    response_snippet: str  # ≤500 chars; provenance anchor


@dataclass(frozen=True)
class GeoReport:
    score: float  # fraction of (model, question) pairs where mentioned
    per_model: list[ModelResult]
    competitor_gaps: list[str] = field(default_factory=list)


ProbeErrorKind = Literal["transport", "invalid_response", "engine_unavailable"]


@dataclass(frozen=True)
class ProbeErrorSource:
    engine: str
    question: str


@dataclass(frozen=True)
class ProbeError:
    kind: ProbeErrorKind
    message: str
    source: ProbeErrorSource

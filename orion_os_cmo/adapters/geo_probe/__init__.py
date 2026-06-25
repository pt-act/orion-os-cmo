"""GEO-probe adapter — AI-answer-engine visibility, grounded in response text."""

from __future__ import annotations

from .adapter import (
    GeoProbeAdapter,
    brand_in,
    extract_competitor_gaps,
    parse_response,
    validate_report,
)
from .types import GeoReport, ModelResult, ProbeError

__all__ = [
    "GeoProbeAdapter",
    "parse_response",
    "brand_in",
    "extract_competitor_gaps",
    "validate_report",
    "GeoReport",
    "ModelResult",
    "ProbeError",
]

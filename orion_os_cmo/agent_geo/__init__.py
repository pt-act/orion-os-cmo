"""agent-geo — AI-answer visibility scoring + grounded GEO fix drafting."""

from __future__ import annotations

from .agent import GeoAgent, SnapshotStore, build_question_battery, validate_findings
from .types import GapRef, GeoAgentError, GeoFindings, GeoFix

__all__ = [
    "GeoAgent",
    "SnapshotStore",
    "build_question_battery",
    "validate_findings",
    "GapRef",
    "GeoAgentError",
    "GeoFindings",
    "GeoFix",
]

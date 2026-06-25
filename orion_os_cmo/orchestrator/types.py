"""Typed contracts for the weekly orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..client_workspace.types import Number

__all__ = [
    "AGENT_ORDER", "AgentOutcome", "Delta", "PrioritizedItem",
    "ApprovalQueueItem", "WeeklyBrief",
]

# Fixed agent order — makes the brief deterministic and the sections complete.
AGENT_ORDER = ["seo", "geo", "reddit", "x", "linkedin", "writer", "coding", "influencer", "ugc"]


@dataclass(frozen=True)
class AgentOutcome:
    """One agent's result: either its typed output, or a structured error string."""
    name: str
    output: Any = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class Delta:
    metric: str
    prior: Number
    current: Number
    delta: float
    source: str


@dataclass(frozen=True)
class PrioritizedItem:
    rank: int
    agent: str
    item_id: str
    summary: str
    action: str  # "review" | "approve" | "merge"


@dataclass(frozen=True)
class ApprovalQueueItem:
    item_id: str
    agent: str
    type: str
    summary: str


@dataclass(frozen=True)
class WeeklyBrief:
    week_key: str
    generated_at: str
    prioritized_items: list[PrioritizedItem]
    per_agent_sections: dict[str, Any]
    week_over_week_deltas: list[Delta]
    approval_queue: list[ApprovalQueueItem] = field(default_factory=list)

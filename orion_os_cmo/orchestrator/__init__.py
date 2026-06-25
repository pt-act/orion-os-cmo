"""weekly-orchestrator — run the weekly pass and emit one consolidated brief.

Integration spec: fan out to the enabled agents, compute week-over-week deltas
from persisted history, merge into a deterministic prioritized brief, persist all
state into client-workspace, and route publishing through the human-gated tools.
"""

from __future__ import annotations

from .agent_runner import run_agent
from .assembler import assemble_brief, render_markdown, summarize
from .coordinator import RunCoordinator
from .delta_engine import compute_deltas
from .publish_gate import PublishGate
from .types import (
    AGENT_ORDER,
    AgentOutcome,
    ApprovalQueueItem,
    Delta,
    PrioritizedItem,
    WeeklyBrief,
)

__all__ = [
    "RunCoordinator",
    "PublishGate",
    "run_agent",
    "compute_deltas",
    "assemble_brief",
    "render_markdown",
    "summarize",
    "AGENT_ORDER",
    "AgentOutcome",
    "ApprovalQueueItem",
    "Delta",
    "PrioritizedItem",
    "WeeklyBrief",
]

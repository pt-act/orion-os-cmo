"""Per-client durable operational workspace (client-workspace spec).

The root unit of the DAG: a typed read/write API over
``.agents/memory_bank-production/`` that every agent and the orchestrator uses to
persist outputs, append metrics, record approvals, and carry run history across
weekly passes.
"""

from __future__ import annotations

from .store import WorkspaceStore
from .types import (
    ApprovalEntry,
    MetricRow,
    OutputItem,
    OutputRow,
    OutputStatus,
    RunRecord,
)

__all__ = [
    "WorkspaceStore",
    "ApprovalEntry",
    "MetricRow",
    "OutputItem",
    "OutputRow",
    "OutputStatus",
    "RunRecord",
]

"""Typed contracts for the per-client production workspace.

Every operational record the CMO persists is one of these frozen dataclasses.
They are the wire format between the agent workers / orchestrator and the durable
``memory_bank-production`` store (H-2 structured output).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

Number = Union[int, float]

OutputStatus = Literal["drafted", "approved", "published", "rejected"]
ApprovalDecision = Literal["approved", "rejected"]


@dataclass(frozen=True)
class MetricRow:
    """One append-only point in the delta time-series.

    ``source`` must point at the tool call that produced the value — a number
    without provenance is confabulation and is refused at write time.
    """

    date: str
    metric: str
    value: Number
    source: str


@dataclass(frozen=True)
class OutputItem:
    """A drafted artifact entering the outputs archive (status starts ``drafted``)."""

    date: str
    agent: str
    type: str
    provenance: str
    link: str = "none"


@dataclass(frozen=True)
class OutputRow:
    """A persisted outputs.md row (an OutputItem plus its assigned id + status)."""

    id: str
    date: str
    agent: str
    type: str
    status: OutputStatus
    provenance: str
    link: str = "none"


@dataclass(frozen=True)
class ApprovalEntry:
    """A human approve/reject decision — the audit trail and liability shield."""

    output_id: str
    decision: ApprovalDecision
    by: str
    note: str = "none"
    tool_result: str = "none"
    date: str = ""


@dataclass(frozen=True)
class RunRecord:
    """One weekly-pass record. Written once per ISO week key (write-once)."""

    week_key: str          # "YYYY-Www"
    week_of: str           # "YYYY-MM-DD"
    inputs: str
    per_agent: list[str] = field(default_factory=list)   # one line per agent
    deltas: str = "none"
    queued_for_approval: str = "none"
    published: str = "none"

"""Typed contracts for agent-coding's PR output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = ["CodeChange", "PREntry", "CodingAgentConfig", "CodingAgentError"]


@dataclass(frozen=True)
class CodeChange:
    finding_id: str
    file_path: str
    change_description: str


@dataclass(frozen=True)
class PREntry:
    pr_url: str
    branch: str
    fixes_applied: list[CodeChange]


@dataclass(frozen=True)
class CodingAgentConfig:
    cap_per_source: int = 5
    base_branch: str = "main"


CodingAgentErrorKind = Literal[
    "strategy_missing", "findings_missing", "llm_error", "pr_failed", "schema_invalid"
]


@dataclass(frozen=True)
class CodingAgentError:
    kind: CodingAgentErrorKind
    message: str
    extra: dict = field(default_factory=dict)

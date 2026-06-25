"""Typed contracts for the github-pr façade (open/update a PR; never merge)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = ["PRResult", "PRErrorKind", "ErrorSource", "PRError", "Transport"]

PRAction = Literal["created", "updated"]


@dataclass(frozen=True)
class PRResult:
    pr_url: str
    action: PRAction
    branch: str


PRErrorKind = Literal["transport", "branch_conflict", "invalid_diff", "api_error", "invalid_response"]


@dataclass(frozen=True)
class ErrorSource:
    api: str
    repo: str
    branch: str


@dataclass(frozen=True)
class PRError:
    kind: PRErrorKind
    message: str
    source: ErrorSource

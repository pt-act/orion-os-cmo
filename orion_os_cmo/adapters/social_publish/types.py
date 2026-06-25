"""Typed contracts for the social-publish façade (gated, irreversible)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = ["PostResult", "PublishErrorKind", "ErrorSource", "PublishError", "Transport", "PLATFORMS"]

PLATFORMS = ("x", "linkedin")


@dataclass(frozen=True)
class PostResult:
    url: str
    id: str


PublishErrorKind = Literal[
    "no_approval", "already_posted", "unsupported_platform",
    "transport", "api_error", "invalid_response",
]


@dataclass(frozen=True)
class ErrorSource:
    platform: str
    item_id: str


@dataclass(frozen=True)
class PublishError:
    kind: PublishErrorKind
    message: str
    source: ErrorSource

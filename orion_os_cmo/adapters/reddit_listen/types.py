"""Typed contracts for the reddit-listen façade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = ["Thread", "RedditSearchResult", "RedditErrorKind", "ErrorSource", "RedditError", "Transport"]


@dataclass(frozen=True)
class Thread:
    url: str
    subreddit: str
    intent: str        # question | complaint | comparison | recommendation | other
    engagement: int    # upvotes or comment count
    snippet: str


@dataclass(frozen=True)
class RedditSearchResult:
    threads: list[Thread]


RedditErrorKind = Literal["transport", "api_error", "invalid_response", "no_results"]


@dataclass(frozen=True)
class ErrorSource:
    tool: str
    query: str


@dataclass(frozen=True)
class RedditError:
    kind: RedditErrorKind
    message: str
    source: ErrorSource

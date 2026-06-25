"""Reddit-listen adapter — typed, sourced Thread[] from one search call."""

from __future__ import annotations

from .adapter import RedditAdapter
from .types import RedditError, RedditSearchResult, Thread

__all__ = ["RedditAdapter", "RedditError", "RedditSearchResult", "Thread"]

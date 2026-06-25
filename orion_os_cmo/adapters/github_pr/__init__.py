"""GitHub-PR adapter — open or update a review-ready PR; never merge."""

from __future__ import annotations

from .adapter import GitHubPrAdapter
from .types import PRError, PRResult

__all__ = ["GitHubPrAdapter", "PRError", "PRResult"]

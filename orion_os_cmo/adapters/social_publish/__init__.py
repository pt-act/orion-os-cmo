"""Social-publish adapter — gated, idempotent X/LinkedIn posting primitive."""

from __future__ import annotations

from .adapter import (
    ApprovalValidator,
    IdempotencyStore,
    SocialPublishAdapter,
)
from .types import PostResult, PublishError

__all__ = [
    "SocialPublishAdapter",
    "ApprovalValidator",
    "IdempotencyStore",
    "PostResult",
    "PublishError",
]

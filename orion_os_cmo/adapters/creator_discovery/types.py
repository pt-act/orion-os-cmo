"""Typed contracts for the creator-discovery façade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = [
    "CreatorSource", "Creator", "CreatorDiscoveryErrorKind",
    "DiscoveryErrorSource", "CreatorDiscoveryError", "Transport",
    "PLATFORMS", "FOLLOWER_TIERS",
]

PLATFORMS = ("instagram", "tiktok")
FOLLOWER_TIERS = ("nano", "micro", "mid", "macro")


@dataclass(frozen=True)
class CreatorSource:
    profile: str                       # tool/URL that produced handle+followers
    email: Optional[str] = None        # tool that produced email
    demographics: Optional[str] = None  # tool that produced audience_fit


@dataclass(frozen=True)
class Creator:
    handle: str
    url: str
    followers: int
    email: Optional[str]
    audience_fit: Optional[float]      # 0.0–1.0; null when demographics unavailable
    source: CreatorSource


CreatorDiscoveryErrorKind = Literal["transport", "invalid_response", "empty_result"]


@dataclass(frozen=True)
class DiscoveryErrorSource:
    provider: str
    niche: str
    platform: str


@dataclass(frozen=True)
class CreatorDiscoveryError:
    kind: CreatorDiscoveryErrorKind
    message: str
    source: DiscoveryErrorSource
